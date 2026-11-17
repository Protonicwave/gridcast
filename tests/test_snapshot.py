import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from factories import all_areas, boundary_collection, payload, shetland_like

from gridcast import snapshot
from gridcast.snapshot import illustrative_range, main

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFIX = "window.GRIDCAST_SNAPSHOT = "
FETCHED_AT = "2026-11-17T11:50Z"


def _boundaries() -> dict[str, Any]:
    return boundary_collection(all_areas(North_Scotland=[shetland_like()]))


def _pilot() -> dict[str, Any]:
    return {
        "caveat": "Stored forecasts only.",
        "errors": {
            "n": 10,
            "mae": 9.28179893574412,
            "mae_ci95_low": 8.9,
            "mae_ci95_high": 9.7,
            "p95_absolute_error": 26.0,
            "mean_bias": 0.97785,
            "mape_percent": 8.4581,
        },
        "mae_by_hour_utc": {str(hour): hour + 0.12345 for hour in range(24)},
        "window_pilot": {
            "window_hours": 3.0,
            "regret_threshold": 0.1,
            "days_analysed": 361,
            "share_regret_at_most_threshold": 0.9196675900277008,
            "share_windows_coincide": 0.26038781163434904,
            "median_regret": 0.013487475915221703,
        },
    }


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "forecast": tmp_path / "forecast.json",
        "boundaries": tmp_path / "boundaries.geojson",
        "pilot": tmp_path / "pilot.json",
        "output": tmp_path / "snapshot.js",
    }
    paths["forecast"].write_text(json.dumps(payload(96)), encoding="utf-8")
    paths["boundaries"].write_text(json.dumps(_boundaries()), encoding="utf-8")
    paths["pilot"].write_text(json.dumps(_pilot()), encoding="utf-8")
    return paths


def _run(inputs: dict[str, Path], fetched_at: str = FETCHED_AT) -> int:
    return main(
        [
            "--fetched-at",
            fetched_at,
            str(inputs["forecast"]),
            str(inputs["boundaries"]),
            str(inputs["pilot"]),
            str(inputs["output"]),
        ]
    )


def _load(output: Path) -> dict[str, Any]:
    text = output.read_text(encoding="utf-8")
    assert text.startswith(PREFIX)
    assert text.endswith(";\n")
    loaded: dict[str, Any] = json.loads(text.removeprefix(PREFIX).removesuffix(";\n"))
    return loaded


def test_writes_snapshot_with_expected_shape(inputs: dict[str, Path]) -> None:
    assert _run(inputs) == 0
    data = _load(inputs["output"])
    assert list(data) == [
        "fetchedAt",
        "firstSlotStart",
        "slotMinutes",
        "fuels",
        "viewBox",
        "shetlandFrame",
        "durationsHours",
        "regions",
        "pilot",
    ]
    assert data["fetchedAt"] == FETCHED_AT
    assert data["firstSlotStart"] == "2026-11-17T11:30Z"
    assert [region["id"] for region in data["regions"]] == list(range(1, 15))
    region = data["regions"][2]
    assert list(region) == [
        "id",
        "name",
        "path",
        "labelAt",
        "forecast",
        "index",
        "mix",
        "windows",
        "illustrativeRange",
    ]
    assert region["name"] == "North West England"
    assert list(region["windows"]) == ["1", "2", "3", "4"]
    assert region["windows"]["2"]["cleanest"] == {"start": 0, "mean": 4.5}
    assert region["windows"]["2"]["dirtiest"] == {"start": 92, "mean": 96.5}
    assert region["windows"]["2"]["timingMatters"] is True
    assert data["pilot"]["mae"] == 9.282
    assert data["pilot"]["maeByHourUtc"][1] == 1.123
    assert data["pilot"]["shareExactBest"] == 0.26
    assert list(data["pilot"]) == [
        "n",
        "mae",
        "maeLow",
        "maeHigh",
        "p95AbsoluteError",
        "maeByHourUtc",
        "windowHours",
        "regretThreshold",
        "shareWithinThreshold",
        "shareExactBest",
    ]


def test_output_is_compact_utf8_with_unix_newline(inputs: dict[str, Path]) -> None:
    assert _run(inputs) == 0
    raw = inputs["output"].read_bytes()
    assert raw.endswith(b";\n")
    assert b"\r" not in raw
    assert b", " not in raw


def test_rejects_fetched_at_before_first_slot(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(inputs, "2026-11-17T11:29Z") == 1
    assert "not inside the first slot" in capsys.readouterr().err
    assert not inputs["output"].exists()


def test_rejects_fetched_at_after_first_slot(inputs: dict[str, Path]) -> None:
    assert _run(inputs, "2026-11-17T12:00Z") == 1


def test_rejects_malformed_fetched_at(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(inputs, "yesterday") == 1
    assert "yesterday" in capsys.readouterr().err


def test_rejects_oversized_input(
    inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(snapshot, "MAX_INPUT_BYTES", 100)
    assert _run(inputs) == 1
    assert "is larger than 100 bytes" in capsys.readouterr().err


def test_reports_missing_input_file(inputs: dict[str, Path]) -> None:
    inputs["pilot"].unlink()
    assert _run(inputs) == 1


def test_rejects_malformed_pilot(inputs: dict[str, Path]) -> None:
    inputs["pilot"].write_text("{}", encoding="utf-8")
    assert _run(inputs) == 1


def _pilot_without(*path: str) -> dict[str, Any]:
    pilot = _pilot()
    target = pilot
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    return pilot


def _pilot_with(value: object, *path: str) -> dict[str, Any]:
    pilot = _pilot()
    target = pilot
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return pilot


PILOT_NUMBER_FIELDS = [
    ("errors", "mae"),
    ("errors", "mae_ci95_low"),
    ("errors", "mae_ci95_high"),
    ("errors", "p95_absolute_error"),
    ("mae_by_hour_utc", "0"),
    ("mae_by_hour_utc", "23"),
    ("window_pilot", "window_hours"),
    ("window_pilot", "regret_threshold"),
    ("window_pilot", "share_regret_at_most_threshold"),
    ("window_pilot", "share_windows_coincide"),
]


@pytest.mark.parametrize("path", [("errors", "n"), *PILOT_NUMBER_FIELDS])
def test_rejects_pilot_field_that_is_missing(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str], path: tuple[str, ...]
) -> None:
    inputs["pilot"].write_text(json.dumps(_pilot_without(*path)), encoding="utf-8")
    assert _run(inputs) == 1
    assert ".".join(path) in capsys.readouterr().err


@pytest.mark.parametrize("path", PILOT_NUMBER_FIELDS)
@pytest.mark.parametrize("bad", ['"9"', "true", "null", "NaN", "Infinity", "-Infinity"])
def test_rejects_pilot_number_that_is_not_a_finite_number(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str], path: tuple[str, ...], bad: str
) -> None:
    text = json.dumps(_pilot_with("PLACEHOLDER", *path)).replace('"PLACEHOLDER"', bad)
    inputs["pilot"].write_text(text, encoding="utf-8")
    assert _run(inputs) == 1
    assert f"pilot file: {'.'.join(path)}" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [0, -4, 2.5, True, "10"])
def test_rejects_pilot_count_that_is_not_a_positive_integer(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str], bad: object
) -> None:
    inputs["pilot"].write_text(json.dumps(_pilot_with(bad, "errors", "n")), encoding="utf-8")
    assert _run(inputs) == 1
    assert "pilot file: errors.n" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_rejects_pilot_threshold_outside_zero_to_one(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str], bad: float
) -> None:
    pilot = _pilot_with(bad, "window_pilot", "regret_threshold")
    inputs["pilot"].write_text(json.dumps(pilot), encoding="utf-8")
    assert _run(inputs) == 1
    assert "pilot file: window_pilot.regret_threshold" in capsys.readouterr().err


@pytest.mark.parametrize("threshold", [0, 1])
def test_accepts_pilot_threshold_at_the_limits(inputs: dict[str, Path], threshold: int) -> None:
    pilot = _pilot_with(threshold, "window_pilot", "regret_threshold")
    inputs["pilot"].write_text(json.dumps(pilot), encoding="utf-8")
    assert _run(inputs) == 0


def test_rejects_pilot_that_is_not_an_object(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    inputs["pilot"].write_text("[1]", encoding="utf-8")
    assert _run(inputs) == 1
    assert "pilot file" in capsys.readouterr().err


def test_rejects_forecast_shorter_than_the_longest_window(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    inputs["forecast"].write_text(json.dumps(payload(7)), encoding="utf-8")
    assert _run(inputs) == 1
    error = capsys.readouterr().err
    assert "region North Scotland" in error
    assert "4-hour window" in error
    assert "8 slots" in error
    assert "7" in error


def test_accepts_forecast_exactly_as_long_as_the_longest_window(inputs: dict[str, Path]) -> None:
    inputs["forecast"].write_text(json.dumps(payload(8)), encoding="utf-8")
    assert _run(inputs) == 0


def test_reports_deeply_nested_input_without_a_traceback(
    inputs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    inputs["pilot"].write_text("[" * 100_000, encoding="utf-8")
    assert _run(inputs) == 1
    error = capsys.readouterr().err
    assert "nested too deeply" in error
    assert str(inputs["pilot"]) in error


def test_illustrative_range_widens_with_lead_time() -> None:
    first = datetime(2026, 11, 17, 11, 30, tzinfo=UTC)
    later = datetime(2026, 11, 19, 11, 0, tzinfo=UTC)
    fetched_at = datetime(2026, 11, 17, 11, 30, tzinfo=UTC)
    (low_now,), (high_now,) = illustrative_range([100], [first], fetched_at)
    (_,), (high_late,) = illustrative_range([100], [later], fetched_at)
    assert high_now - 100 == pytest.approx(100 - low_now, abs=0.1)
    assert high_late - 100 > high_now - 100
    # Capped at 48 hours ahead: 1.2816 * sqrt(pi / 2) * 14 = 22.5 (rounded).
    assert high_late == pytest.approx(122.5, abs=0.1)


def test_illustrative_range_never_goes_below_zero() -> None:
    start = datetime(2026, 11, 17, 11, 30, tzinfo=UTC)
    (low,), _ = illustrative_range([3], [start], start)
    assert low == 0.0


def test_real_data_gives_a_complete_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.js"
    data_dir = REPO_ROOT / "data"
    status = main(
        [
            "--fetched-at",
            FETCHED_AT,
            str(data_dir / "regional_fw48h_20261117T1150Z.json"),
            str(data_dir / "gb-dno-license-areas-20240503.geojson"),
            str(data_dir / "pilot_national_2025.json"),
            str(output),
        ]
    )
    assert status == 0
    data = _load(output)
    assert len(data["regions"]) == 14
    for region in data["regions"]:
        assert len(region["forecast"]) == 96
        assert region["path"]
        assert len(region["labelAt"]) == 2
        for hours, window in region["windows"].items():
            slots = int(hours) * 2
            assert window["cleanest"]["start"] + slots <= 96
            assert window["dirtiest"]["start"] + slots <= 96
        low, high = region["illustrativeRange"]["low"], region["illustrativeRange"]["high"]
        assert all(
            lo <= value <= hi for lo, value, hi in zip(low, region["forecast"], high, strict=True)
        )
