from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from factories import payload, slot

from gridcast.forecast import (
    FUELS,
    format_slot_time,
    parse_forecast,
    parse_slot_time,
)


def test_parses_valid_payload() -> None:
    parsed = parse_forecast(payload(2))
    assert parsed.slot_starts == (
        datetime(2026, 11, 17, 11, 30, tzinfo=UTC),
        datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
    )
    assert sorted(parsed.series) == list(range(1, 15))
    third = parsed.series[3]
    assert third.forecast == (3, 4)
    assert third.index == ("moderate", "moderate")
    assert len(third.mix) == 2
    assert len(third.mix[0]) == len(FUELS)


def test_ignores_aggregate_regions() -> None:
    assert 15 not in parse_forecast(payload(1)).series


def test_orders_mix_by_fuels_not_by_payload_order() -> None:
    data = payload(1)
    entry = data["data"][0]["regions"][0]
    entry["generationmix"] = [
        {"fuel": fuel, "perc": float(position)}
        for position, fuel in reversed(list(enumerate(FUELS)))
    ]
    assert parse_forecast(data).series[1].mix[0] == tuple(float(p) for p in range(len(FUELS)))


def _rejects(data: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_forecast(data)


def test_rejects_non_object_payload() -> None:
    _rejects([1, 2], r"payload: expected an object, got \[1, 2\]")


def test_rejects_missing_data_key() -> None:
    _rejects({}, "missing key 'data'")


def test_rejects_non_list_data() -> None:
    _rejects({"data": "abc"}, "expected a list, got 'abc'")


def test_rejects_empty_data() -> None:
    _rejects({"data": []}, "no slots")


def test_rejects_missing_slot_time() -> None:
    data = payload(1)
    del data["data"][0]["from"]
    _rejects(data, "missing key 'from'")


def test_rejects_non_string_slot_time() -> None:
    data = payload(1)
    data["data"][0]["from"] = 5
    _rejects(data, "expected a time string, got 5")


def test_rejects_malformed_slot_time() -> None:
    data = payload(1)
    data["data"][0]["from"] = "17 Nov"
    _rejects(data, "17 Nov")


def test_rejects_gap_between_slots() -> None:
    data = {"data": [slot(0), slot(2)]}
    _rejects(data, "expected start 2026-11-17T12:00Z, got 2026-11-17T12:30Z")


def test_rejects_out_of_order_slots() -> None:
    _rejects({"data": [slot(1), slot(0)]}, "got 2026-11-17T11:30Z")


def test_rejects_duplicated_slot() -> None:
    _rejects({"data": [slot(0), slot(0)]}, "got 2026-11-17T11:30Z")


def test_rejects_slot_missing_a_region() -> None:
    data = {"data": [slot(0, region_ids=range(1, 14))]}
    _rejects(data, r"missing regions \[14\]")


def test_rejects_repeated_region_in_slot() -> None:
    data = payload(1)
    data["data"][0]["regions"].append(deepcopy(data["data"][0]["regions"][0]))
    _rejects(data, "region 1 appears twice")


def test_rejects_non_integer_region_id() -> None:
    data = payload(1)
    data["data"][0]["regions"][0]["regionid"] = "1"
    _rejects(data, "expected an integer, got '1'")


def _with_intensity(**changes: Any) -> dict[str, Any]:
    data = payload(1)
    data["data"][0]["regions"][0]["intensity"].update(changes)
    return data


def test_rejects_unknown_index() -> None:
    _rejects(_with_intensity(index="extreme"), "got 'extreme'")


def test_rejects_non_string_index() -> None:
    _rejects(_with_intensity(index=["low"]), r"got \['low'\]")


def test_rejects_negative_forecast() -> None:
    _rejects(_with_intensity(forecast=-1), "non-negative forecast, got -1")


@pytest.mark.parametrize("value", [12.5, "12", None, True])
def test_rejects_non_integer_forecast(value: object) -> None:
    _rejects(_with_intensity(forecast=value), "expected an integer")


def test_rejects_fuel_missing_from_mix() -> None:
    data = payload(1)
    data["data"][0]["regions"][0]["generationmix"].pop()
    _rejects(data, "missing fuel 'wind'")


def test_rejects_non_numeric_percentage() -> None:
    data = payload(1)
    data["data"][0]["regions"][0]["generationmix"][0]["perc"] = "x"
    _rejects(data, "biomass: expected a number, got 'x'")


def test_rejects_boolean_percentage() -> None:
    data = payload(1)
    data["data"][0]["regions"][0]["generationmix"][0]["perc"] = True
    _rejects(data, "expected a number")


def test_shortens_overlong_offending_value() -> None:
    _rejects({"data": "x" * 500}, r"'x+\.\.\.")


def test_slot_time_round_trips() -> None:
    assert format_slot_time(parse_slot_time("2026-11-17T11:50Z")) == "2026-11-17T11:50Z"
