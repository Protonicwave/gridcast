"""Parsing and validation of the Carbon Intensity API regional 48-hour forecast."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from gridcast.regions import REGIONS

FUELS = ("biomass", "coal", "imports", "gas", "nuclear", "other", "hydro", "solar", "wind")
INDEX_LEVELS = ("very low", "low", "moderate", "high", "very high")
SLOT_MINUTES = 30
TIME_FORMAT = "%Y-%m-%dT%H:%MZ"

_SLOT = timedelta(minutes=SLOT_MINUTES)
# The API also returns England, Scotland, Wales and GB aggregates under other ids.
_REGION_IDS = frozenset(region.api_id for region in REGIONS)
_MAX_SHOWN_CHARS = 80


@dataclass(frozen=True, slots=True)
class RegionSeries:
    """One region across all slots; `mix` holds percentages in FUELS order."""

    forecast: tuple[int, ...]
    index: tuple[str, ...]
    mix: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class RegionalForecast:
    """Validated forecast for regions 1 to 14, keyed by region id."""

    slot_starts: tuple[datetime, ...]
    series: dict[int, RegionSeries]


def parse_slot_time(value: object) -> datetime:
    """Parse a "YYYY-MM-DDTHH:MMZ" string as an aware UTC datetime."""
    if not isinstance(value, str):
        raise ValueError(f"expected a time string, got {_shown(value)}")
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=UTC)


def format_slot_time(moment: datetime) -> str:
    """Format an aware UTC datetime as "YYYY-MM-DDTHH:MMZ"."""
    return moment.strftime(TIME_FORMAT)


def parse_forecast(payload: object) -> RegionalForecast:
    """Validate a regional fw48h payload. Raises ValueError naming the offending value."""
    slots = _as_list(_member(payload, "data", "payload"), "data")
    if not slots:
        raise ValueError("data holds no slots")
    starts: list[datetime] = []
    forecast: dict[int, list[int]] = {region_id: [] for region_id in _REGION_IDS}
    index: dict[int, list[str]] = {region_id: [] for region_id in _REGION_IDS}
    mix: dict[int, list[tuple[float, ...]]] = {region_id: [] for region_id in _REGION_IDS}
    for position, slot in enumerate(slots):
        where = f"slot {position}"
        start = parse_slot_time(_member(slot, "from", where))
        if starts and start != starts[-1] + _SLOT:
            raise ValueError(
                f"{where}: expected start {format_slot_time(starts[-1] + _SLOT)}, "
                f"got {format_slot_time(start)}"
            )
        starts.append(start)
        for region_id, entry in _regions_of(slot, where).items():
            where_region = f"{where} region {region_id}"
            intensity = _member(entry, "intensity", where_region)
            forecast[region_id].append(_forecast_value(intensity, where_region))
            index[region_id].append(_index_level(intensity, where_region))
            mix[region_id].append(_mix_of(entry, where_region))
    series = {
        region_id: RegionSeries(
            tuple(forecast[region_id]), tuple(index[region_id]), tuple(mix[region_id])
        )
        for region_id in sorted(_REGION_IDS)
    }
    return RegionalForecast(slot_starts=tuple(starts), series=series)


def _shown(value: object) -> str:
    text = repr(value)
    return text if len(text) <= _MAX_SHOWN_CHARS else text[:_MAX_SHOWN_CHARS] + "..."


def _member(obj: object, key: str, where: str) -> object:
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: expected an object, got {_shown(obj)}")
    if key not in obj:
        raise ValueError(f"{where}: missing key {key!r}")
    return obj[key]


def _as_list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a list, got {_shown(value)}")
    return value


def _as_int(value: object, where: str) -> int:
    # bool is an int subclass, and true is not a count.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{where}: expected an integer, got {_shown(value)}")
    return value


def _as_number(value: object, where: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{where}: expected a number, got {_shown(value)}")
    return float(value)


def _regions_of(slot: object, where: str) -> dict[int, object]:
    found: dict[int, object] = {}
    for entry in _as_list(_member(slot, "regions", where), f"{where} regions"):
        region_id = _as_int(_member(entry, "regionid", where), f"{where} regionid")
        if region_id not in _REGION_IDS:
            continue
        if region_id in found:
            raise ValueError(f"{where}: region {region_id} appears twice")
        found[region_id] = entry
    missing = sorted(_REGION_IDS - found.keys())
    if missing:
        raise ValueError(f"{where}: missing regions {missing}")
    return found


def _forecast_value(intensity: object, where: str) -> int:
    value = _as_int(_member(intensity, "forecast", where), f"{where} forecast")
    if value < 0:
        raise ValueError(f"{where}: expected a non-negative forecast, got {value}")
    return value


def _index_level(intensity: object, where: str) -> str:
    level = _member(intensity, "index", where)
    if not isinstance(level, str) or level not in INDEX_LEVELS:
        raise ValueError(f"{where}: expected an index in {INDEX_LEVELS}, got {_shown(level)}")
    return level


def _mix_of(entry: object, where: str) -> tuple[float, ...]:
    items = _as_list(_member(entry, "generationmix", where), f"{where} generationmix")
    pairs = [(_member(item, "fuel", where), _member(item, "perc", where)) for item in items]
    percentages: list[float] = []
    for fuel in FUELS:
        matches = [perc for name, perc in pairs if name == fuel]
        if not matches:
            raise ValueError(f"{where}: generationmix is missing fuel {fuel!r}")
        percentages.append(_as_number(matches[0], f"{where} {fuel}"))
    return tuple(percentages)
