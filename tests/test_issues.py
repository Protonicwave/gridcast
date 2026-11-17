import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from factories import FIRST_SLOT, payload, slot

from gridcast.issues import Issue, parse_regional_issues

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
