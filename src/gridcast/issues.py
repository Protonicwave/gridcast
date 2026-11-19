"""Forecast issues and actuals, as archived, parsed from Carbon Intensity API responses."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from gridcast._payload import as_int, as_list, forecast_value, member
from gridcast.forecast import format_slot_time, parse_slot_start

# Which of NESO's forecasts an issue comes from.
IssueFeed = Literal["regional", "national"]

# The regional endpoint returns the 14 regions and then England, Scotland, Wales and GB.
REGIONAL_AREA_IDS = frozenset(range(1, 19))
# The regional endpoint's area for Great Britain, which the national forecast is filed under.
GREAT_BRITAIN_AREA_ID = 18
# The archive stores intensities as PostgreSQL smallint.
MAX_INTENSITY_G_PER_KWH = 32_767


@dataclass(frozen=True, slots=True)
class Issue:
    """One area's forecast as published: an intensity per half hour from `first_slot`."""

    feed: IssueFeed
    area_id: int
    first_slot: datetime
    intensities_g_per_kwh: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StoredIssue:
    """An archived issue with the time it was fetched, which is when it was issued."""

    first_slot: datetime
    intensities_g_per_kwh: tuple[int, ...]
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class Actual:
    """The measured national intensity of the half hour starting at `slot_start`.

    `intensity_g_per_kwh` is None until NESO publishes the measurement.
    """

    slot_start: datetime
    intensity_g_per_kwh: int | None


@dataclass(frozen=True, slots=True)
class Parsed:
    """What one API response holds: forecast issues, actuals, or neither if it failed."""

    issues: tuple[Issue, ...] = ()
    actuals: tuple[Actual, ...] = ()


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
    return _forecast(member(entry, "intensity", where), where)


def _forecast(intensity: object, where: str) -> int:
    return _within_smallint(forecast_value(intensity, where), "forecast", where)


def _within_smallint(value: int, name: str, where: str) -> int:
    if value > MAX_INTENSITY_G_PER_KWH:
        raise ValueError(
            f"{where}: expected a {name} of at most {MAX_INTENSITY_G_PER_KWH}, got {value}"
        )
    return value


def parse_national_issue(payload: object) -> Issue:
    """The national fw48h forecast as one issue for Great Britain.

    Raises ValueError naming the offending value if the payload is malformed.
    """
    starts, intensities = _national_slots(payload)
    values = tuple(
        _forecast(intensity, f"slot {position} ({format_slot_time(start)})")
        for position, (start, intensity) in enumerate(zip(starts, intensities, strict=True))
    )
    return Issue("national", GREAT_BRITAIN_AREA_ID, starts[0], values)


def parse_national_actuals(payload: object) -> tuple[Actual, ...]:
    """The measured intensity of each half hour in a national intensity payload.

    Raises ValueError naming the offending value if the payload is malformed.
    """
    starts, intensities = _national_slots(payload)
    return tuple(
        Actual(start, _actual(intensity, f"slot {position} ({format_slot_time(start)})"))
        for position, (start, intensity) in enumerate(zip(starts, intensities, strict=True))
    )


def _national_slots(payload: object) -> tuple[list[datetime], list[object]]:
    slots = as_list(member(payload, "data", "payload"), "data")
    if not slots:
        raise ValueError("data holds no slots")
    starts: list[datetime] = []
    for position, slot in enumerate(slots):
        starts.append(parse_slot_start(slot, position, starts[-1] if starts else None))
    intensities = [
        member(slot, "intensity", f"slot {position}") for position, slot in enumerate(slots)
    ]
    return starts, intensities


def _actual(intensity: object, where: str) -> int | None:
    value = member(intensity, "actual", where)
    if value is None:
        return None
    value = as_int(value, f"{where} actual")
    if value < 0:
        raise ValueError(f"{where}: expected a non-negative actual, got {value}")
    return _within_smallint(value, "actual", where)
