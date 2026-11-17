"""Parsing and validation of the Carbon Intensity API regional 48-hour forecast."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from gridcast._payload import as_int, as_list, forecast_value, member, shown
from gridcast.regions import REGIONS

FUELS = ("biomass", "coal", "imports", "gas", "nuclear", "other", "hydro", "solar", "wind")
IndexLevel = Literal["very low", "low", "moderate", "high", "very high"]
INDEX_LEVELS: tuple[IndexLevel, ...] = ("very low", "low", "moderate", "high", "very high")
SLOT_MINUTES = 30
TIME_FORMAT = "%Y-%m-%dT%H:%MZ"

_SLOT = timedelta(minutes=SLOT_MINUTES)
# The API also returns England, Scotland, Wales and GB aggregates under other ids.
_REGION_IDS = frozenset(region.api_id for region in REGIONS)
_MAX_PERCENTAGE = 100


@dataclass(frozen=True, slots=True)
class RegionSeries:
    """One region across all slots; `mix` holds percentages in FUELS order."""

    forecast: tuple[int, ...]
    index: tuple[IndexLevel, ...]
    mix: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class RegionalForecast:
    """Validated forecast for regions 1 to 14, keyed by region id."""

    slot_starts: tuple[datetime, ...]
    series: dict[int, RegionSeries]


def parse_slot_time(value: object) -> datetime:
    """Parse a "YYYY-MM-DDTHH:MMZ" string as an aware UTC datetime."""
    if not isinstance(value, str):
        raise ValueError(f"expected a time string, got {shown(value)}")
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=UTC)


def format_slot_time(moment: datetime) -> str:
    """Format an aware UTC datetime as "YYYY-MM-DDTHH:MMZ"."""
    return moment.strftime(TIME_FORMAT)


def parse_forecast(payload: object) -> RegionalForecast:
    """Validate a regional fw48h payload. Raises ValueError naming the offending value."""
    slots = as_list(member(payload, "data", "payload"), "data")
    if not slots:
        raise ValueError("data holds no slots")
    starts: list[datetime] = []
    forecast: dict[int, list[int]] = {region_id: [] for region_id in _REGION_IDS}
    index: dict[int, list[IndexLevel]] = {region_id: [] for region_id in _REGION_IDS}
    mix: dict[int, list[tuple[float, ...]]] = {region_id: [] for region_id in _REGION_IDS}
    for position, slot in enumerate(slots):
        start = parse_slot_start(slot, position, starts[-1] if starts else None)
        starts.append(start)
        where = f"slot {position} ({format_slot_time(start)})"
        for region_id, entry in _regions_of(slot, where).items():
            where_region = f"{where} region {region_id}"
            intensity = member(entry, "intensity", where_region)
            forecast[region_id].append(forecast_value(intensity, where_region))
            index[region_id].append(_index_level(intensity, where_region))
            mix[region_id].append(_mix_of(entry, where_region))
    series = {
        region_id: RegionSeries(
            tuple(forecast[region_id]), tuple(index[region_id]), tuple(mix[region_id])
        )
        for region_id in sorted(_REGION_IDS)
    }
    return RegionalForecast(slot_starts=tuple(starts), series=series)


def parse_slot_start(slot: object, position: int, previous: datetime | None) -> datetime:
    """Slot `position`'s start: one slot after `previous`, or on a half hour if it is first."""
    where = f"slot {position}"
    raw_start = member(slot, "from", where)
    try:
        start = parse_slot_time(raw_start)
    except ValueError as err:
        raise ValueError(f"{where} from: {err}") from err
    if previous is None:
        if start.minute % SLOT_MINUTES != 0:
            raise ValueError(
                f"{where}: expected a first start on the hour or half hour, "
                f"got {format_slot_time(start)}"
            )
    elif start != previous + _SLOT:
        raise ValueError(
            f"{where}: expected start {format_slot_time(previous + _SLOT)}, "
            f"got {format_slot_time(start)}"
        )
    return start


def _as_number(value: object, where: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{where}: expected a number, got {shown(value)}")
    return float(value)


def _regions_of(slot: object, where: str) -> dict[int, object]:
    found: dict[int, object] = {}
    for entry in as_list(member(slot, "regions", where), f"{where} regions"):
        region_id = as_int(member(entry, "regionid", where), f"{where} regionid")
        if region_id not in _REGION_IDS:
            continue
        if region_id in found:
            raise ValueError(f"{where}: region {region_id} appears twice")
        found[region_id] = entry
    missing = sorted(_REGION_IDS - found.keys())
    if missing:
        raise ValueError(f"{where}: missing regions {missing}")
    return found


def _index_level(intensity: object, where: str) -> IndexLevel:
    level = member(intensity, "index", where)
    for known in INDEX_LEVELS:
        if level == known:
            return known
    raise ValueError(f"{where}: expected an index in {INDEX_LEVELS}, got {shown(level)}")


def _mix_of(entry: object, where: str) -> tuple[float, ...]:
    items = as_list(member(entry, "generationmix", where), f"{where} generationmix")
    percentages: dict[str, float] = {}
    for item in items:
        fuel = member(item, "fuel", where)
        if not isinstance(fuel, str) or fuel not in FUELS:
            raise ValueError(f"{where}: expected a fuel in {FUELS}, got {shown(fuel)}")
        if fuel in percentages:
            raise ValueError(f"{where}: generationmix lists fuel {fuel!r} twice")
        percentage = _as_number(member(item, "perc", where), f"{where} {fuel}")
        if not 0 <= percentage <= _MAX_PERCENTAGE:
            raise ValueError(
                f"{where} {fuel}: expected a percentage from 0 to {_MAX_PERCENTAGE}, "
                f"got {percentage}"
            )
        percentages[fuel] = percentage
    for fuel in FUELS:
        if fuel not in percentages:
            raise ValueError(f"{where}: generationmix is missing fuel {fuel!r}")
    return tuple(percentages[fuel] for fuel in FUELS)
