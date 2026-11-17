"""Builders for small valid inputs shared by the tests."""

from datetime import UTC, datetime, timedelta
from typing import Any

from gridcast.forecast import FUELS, SLOT_MINUTES, format_slot_time
from gridcast.regions import REGIONS

FIRST_SLOT = datetime(2026, 11, 17, 11, 30, tzinfo=UTC)
KM = 1000.0
BNG_CRS = "urn:ogc:def:crs:EPSG::27700"


def region_entry(region_id: int, forecast: int = 100) -> dict[str, Any]:
    return {
        "regionid": region_id,
        "shortname": f"Region {region_id}",
        "intensity": {"forecast": forecast, "index": "moderate"},
        "generationmix": [{"fuel": fuel, "perc": 100 / len(FUELS)} for fuel in FUELS],
    }


def slot(position: int, region_ids: range = range(1, 19)) -> dict[str, Any]:
    start = FIRST_SLOT + timedelta(minutes=SLOT_MINUTES * position)
    return {
        "from": format_slot_time(start),
        "to": format_slot_time(start + timedelta(minutes=SLOT_MINUTES)),
        "regions": [
            region_entry(region_id, forecast=position + region_id) for region_id in region_ids
        ],
    }


def payload(slot_count: int = 2) -> dict[str, Any]:
    return {"data": [slot(position) for position in range(slot_count)]}


def square(west: float, south: float, side_m: float) -> list[list[float]]:
    east, north = west + side_m, south + side_m
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def shetland_like(west: float = 450_000.0) -> list[list[float]]:
    return square(west, 1_150_000.0, 30 * KM)


def boundary_collection(
    placements: dict[str, list[list[list[float]]]], crs: str = BNG_CRS
) -> dict[str, Any]:
    """One MultiPolygon feature per area, each holding the given exterior rings."""
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": [
            {
                "type": "Feature",
                "properties": {"Area": area},
                "geometry": {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]},
            }
            for area, rings in placements.items()
        ],
    }


def all_areas(**extra: list[list[list[float]]]) -> dict[str, list[list[list[float]]]]:
    """Every area as a 40 km square on a diagonal, plus any extra rings for named areas."""
    placements = {
        region.boundary_area: [square(50_000 * region.api_id, 50_000 * region.api_id, 40 * KM)]
        for region in REGIONS
    }
    for area, rings in extra.items():
        placements[area.replace("_", " ")] += rings
    return placements
