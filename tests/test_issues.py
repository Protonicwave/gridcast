import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from factories import FIRST_SLOT, national_payload, payload, slot

from gridcast.issues import (
    Actual,
    Issue,
    parse_national_actuals,
    parse_national_issue,
    parse_regional_issues,
)

SAVED_RESPONSE = Path(__file__).parent.parent / "data" / "regional_fw48h_20261117T1150Z.json"


def test_parses_one_issue_per_area_with_intensities_in_slot_order() -> None:
    issues = parse_regional_issues(payload(3))
    assert [issue.area_id for issue in issues] == list(range(1, 19))
    # The factory gives area n in slot p a forecast of n + p.
    assert issues[6] == Issue("regional", 7, FIRST_SLOT, (7, 8, 9))
    assert {issue.first_slot for issue in issues} == {FIRST_SLOT}


def test_parses_saved_response() -> None:
    saved = json.loads(SAVED_RESPONSE.read_text(encoding="utf-8"))
    issues = parse_regional_issues(saved)
    assert len(issues) == 18
    assert {len(issue.intensities_g_per_kwh) for issue in issues} == {96}
    south_wales = issues[6]
    assert south_wales.first_slot == datetime(2026, 11, 17, 11, 30, tzinfo=UTC)
    assert south_wales.intensities_g_per_kwh[0] == 281


def test_accepts_a_single_slot() -> None:
    issues = parse_regional_issues(payload(1))
    assert issues[0].intensities_g_per_kwh == (1,)


def test_accepts_the_largest_storable_intensity() -> None:
    data = payload(1)
    data["data"][0]["regions"][0]["intensity"]["forecast"] = 32_767
    assert parse_regional_issues(data)[0].intensities_g_per_kwh == (32_767,)


def _set_forecast(value: object) -> Callable[[dict[str, Any]], None]:
    def change(data: dict[str, Any]) -> None:
        data["data"][1]["regions"][2]["intensity"]["forecast"] = value

    return change


def _drop_area(data: dict[str, Any]) -> None:
    del data["data"][1]["regions"][4]


def _repeat_area(data: dict[str, Any]) -> None:
    data["data"][1]["regions"].append(data["data"][1]["regions"][0])


def _add_unknown_area(data: dict[str, Any]) -> None:
    data["data"][1]["regions"].append({"regionid": 19, "intensity": {"forecast": 1}})


def _swap_slots(data: dict[str, Any]) -> None:
    data["data"][0], data["data"][1] = data["data"][1], data["data"][0]


def _leave_gap(data: dict[str, Any]) -> None:
    data["data"][1] = slot(2)


def _drop_intensity(data: dict[str, Any]) -> None:
    del data["data"][1]["regions"][2]["intensity"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_set_forecast(-1), r"slot 1 \(2026-11-17T12:00Z\) area 3: .*non-negative.*got -1"),
        (_set_forecast(32_768), r"area 3: expected a forecast of at most 32767, got 32768"),
        (_set_forecast(12.5), r"area 3 forecast: expected an integer, got 12.5"),
        (_set_forecast(True), r"area 3 forecast: expected an integer, got True"),
        (_set_forecast(None), r"area 3 forecast: expected an integer, got None"),
        (_drop_intensity, r"area 3: missing key 'intensity'"),
        (_drop_area, r"slot 1 \(2026-11-17T12:00Z\): missing areas \[5\]"),
        (_repeat_area, r"slot 1 \(2026-11-17T12:00Z\): area 1 appears twice"),
        (_add_unknown_area, r"expected an area id from 1 to 18, got 19"),
        (_swap_slots, r"slot 1: expected start 2026-11-17T12:30Z, got 2026-11-17T11:30Z"),
        (_leave_gap, r"slot 1: expected start 2026-11-17T12:00Z, got 2026-11-17T12:30Z"),
    ],
)
def test_rejects_malformed_payload_naming_the_value(
    change: Callable[[dict[str, Any]], None], message: str
) -> None:
    data = payload(3)
    change(data)
    with pytest.raises(ValueError, match=message):
        parse_regional_issues(data)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], r"payload: expected an object, got \[\]"),
        ({}, r"payload: missing key 'data'"),
        ({"data": {}}, r"data: expected a list, got \{\}"),
        ({"data": []}, r"data holds no slots"),
        ({"data": [{"from": "2026-11-17T11:30Z"}]}, r"missing key 'regions'"),
        ({"data": [{"from": "yesterday", "regions": []}]}, r"slot 0 from: .*'yesterday'"),
    ],
)
def test_rejects_wrong_shape_naming_the_value(data: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_regional_issues(data)


def test_parses_the_national_forecast_as_one_issue_for_great_britain() -> None:
    issue = parse_national_issue(national_payload(150, None, None))
    assert issue == Issue("national", 18, FIRST_SLOT, (200, 201, 202))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data.update(data=[]), "data holds no slots"),
        (lambda data: data["data"][1].pop("intensity"), "slot 1: missing key 'intensity'"),
        (
            lambda data: data["data"][1]["intensity"].update(forecast=None),
            "slot 1 (2026-11-17T12:00Z) forecast: expected an integer, got None",
        ),
        (
            lambda data: data["data"][1]["intensity"].update(forecast=-4),
            "expected a non-negative forecast, got -4",
        ),
        (
            lambda data: data["data"][1]["intensity"].update(forecast=32_768),
            "expected a forecast of at most 32767, got 32768",
        ),
        (
            lambda data: data["data"][0].update({"from": "2026-11-17T11:10Z"}),
            "expected a first start on the hour or half hour",
        ),
    ],
)
def test_rejects_a_malformed_national_forecast_naming_the_value(
    change: Callable[[dict[str, Any]], object], message: str
) -> None:
    data = national_payload(None, None, None)
    change(data)
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_national_issue(data)


def test_parses_national_actuals_keeping_a_missing_one_as_none() -> None:
    actuals = parse_national_actuals(national_payload(150, 160, None))
    assert actuals == (
        Actual(FIRST_SLOT, 150),
        Actual(FIRST_SLOT + timedelta(minutes=30), 160),
        Actual(FIRST_SLOT + timedelta(minutes=60), None),
    )


@pytest.mark.parametrize(
    ("actual", "message"),
    [("high", "got 'high'"), (-1, "non-negative actual, got -1"), (32_768, "at most 32767")],
)
def test_rejects_a_malformed_actual_naming_the_value(actual: object, message: str) -> None:
    data = national_payload(150, 160)
    data["data"][1]["intensity"]["actual"] = actual
    with pytest.raises(ValueError, match=message):
        parse_national_actuals(data)


def test_rejects_national_actuals_with_no_slots() -> None:
    with pytest.raises(ValueError, match="data holds no slots"):
        parse_national_actuals({"data": []})


def test_rejects_national_actuals_with_a_gap() -> None:
    data = national_payload(150, 160, 170)
    del data["data"][1]
    with pytest.raises(ValueError, match="slot 1: expected start 2026-11-17T12:00Z"):
        parse_national_actuals(data)
