"""Forecast issues, as archived, parsed from Carbon Intensity API responses."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from gridcast._payload import as_int, as_list, forecast_value, member
from gridcast.forecast import format_slot_time, parse_slot_start

# Which of NESO's forecasts an issue comes from.
IssueFeed = Literal["regional"]

# The regional endpoint returns the 14 regions and then England, Scotland, Wales and GB.
REGIONAL_AREA_IDS = frozenset(range(1, 19))
# The archive stores intensities as PostgreSQL smallint.
MAX_INTENSITY_G_PER_KWH = 32_767


@dataclass(frozen=True, slots=True)
class Issue:
    """One area's forecast as published: an intensity per half hour from `first_slot`."""

    feed: IssueFeed
    area_id: int
    first_slot: datetime
    intensities_g_per_kwh: tuple[int, ...]


def parse_regional_issues(payload: object) -> tuple[Issue, ...]:
    """One issue per area of a regional fw48h payload, in area order.

    Raises ValueError naming the offending value if any slot or area is malformed,
    missing, repeated or unknown.
    """
    slots = as_list(member(payload, "data", "payload"), "data")
    if not slots:
        raise ValueError("data holds no slots")
    starts: list[datetime] = []
    intensities: dict[int, list[int]] = {area_id: [] for area_id in REGIONAL_AREA_IDS}
    for position, slot in enumerate(slots):
        start = parse_slot_start(slot, position, starts[-1] if starts else None)
        starts.append(start)
        where = f"slot {position} ({format_slot_time(start)})"
        for area_id, entry in _areas_of(slot, where).items():
            intensities[area_id].append(_intensity(entry, f"{where} area {area_id}"))
    return tuple(
        Issue("regional", area_id, starts[0], tuple(intensities[area_id]))
        for area_id in sorted(REGIONAL_AREA_IDS)
    )


def _areas_of(slot: object, where: str) -> dict[int, object]:
    found: dict[int, object] = {}
    for entry in as_list(member(slot, "regions", where), f"{where} regions"):
        area_id = as_int(member(entry, "regionid", where), f"{where} regionid")
        if area_id not in REGIONAL_AREA_IDS:
            raise ValueError(f"{where}: expected an area id from 1 to 18, got {area_id}")
        if area_id in found:
            raise ValueError(f"{where}: area {area_id} appears twice")
        found[area_id] = entry
    missing = sorted(REGIONAL_AREA_IDS - found.keys())
    if missing:
        raise ValueError(f"{where}: missing areas {missing}")
    return found


def _intensity(entry: object, where: str) -> int:
    value = forecast_value(member(entry, "intensity", where), where)
    if value > MAX_INTENSITY_G_PER_KWH:
        raise ValueError(
            f"{where}: expected a forecast of at most {MAX_INTENSITY_G_PER_KWH}, got {value}"
        )
    return value
