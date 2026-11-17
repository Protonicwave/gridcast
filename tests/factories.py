"""Builders for small valid inputs shared by the tests."""

from datetime import UTC, datetime, timedelta
from typing import Any

from gridcast.forecast import FUELS

FIRST_SLOT = datetime(2026, 11, 17, 11, 30, tzinfo=UTC)


def _time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%MZ")


def region_entry(region_id: int, forecast: int = 100) -> dict[str, Any]:
    return {
        "regionid": region_id,
        "shortname": f"Region {region_id}",
        "intensity": {"forecast": forecast, "index": "moderate"},
        "generationmix": [{"fuel": fuel, "perc": 100 / len(FUELS)} for fuel in FUELS],
    }


def slot(position: int, region_ids: range = range(1, 19)) -> dict[str, Any]:
    start = FIRST_SLOT + timedelta(minutes=30 * position)
    return {
        "from": _time(start),
        "to": _time(start + timedelta(minutes=30)),
        "regions": [
            region_entry(region_id, forecast=position + region_id) for region_id in region_ids
        ],
    }


def payload(slot_count: int = 2) -> dict[str, Any]:
    return {"data": [slot(position) for position in range(slot_count)]}
