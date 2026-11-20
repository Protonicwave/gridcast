"""Region boundaries from British National Grid GeoJSON to simplified SVG paths."""

import argparse
import json
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from gridcast.regions import REGIONS

SIMPLIFY_TOLERANCE_M = 1500.0
MIN_RING_AREA_M2 = 20_000_000.0
SHETLAND_MIN_NORTHING_M = 1_100_000.0
SHETLAND_SHIFT_NORTHING_M = -220_000.0
SHETLAND_FRAME_PADDING_M = 5_000.0
VIEW_MARGIN_M = 5_000.0

_METRES_PER_UNIT = 1000.0
_BOUNDARY_AREAS = frozenset(region.boundary_area for region in REGIONS)
# A closed ring needs three distinct points plus the repeated first point.
_MIN_RING_POINTS = 4

Point = tuple[float, float]
# A closed ring repeats its first point at the end, as GeoJSON does.
Ring = list[Point]
# The first ring is the exterior and any others are holes.
Polygon = list[Ring]
# Left, top, width, height in SVG units.
Frame = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class RegionShape:
    """SVG path (draw with fill-rule evenodd) and a label point inside the region."""

    path: str
    label_at: Point


@dataclass(frozen=True, slots=True)
class MapGeometry:
    """Projected regions keyed by boundary area name, with the SVG view box and inset frame."""

    view_box: Frame
    shetland_frame: Frame
    regions: dict[str, RegionShape]


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point: write the site's map shapes. Returns the process exit status."""
    args = _parser().parse_args(argv)
    try:
        geometry = build_map(json.loads(args.boundaries.read_text(encoding="utf-8")))
        args.output.write_text(
            json.dumps(map_shapes(geometry), separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except (OSError, ValueError) as err:
        print(f"gridcast-map: {args.boundaries}: {err}", file=sys.stderr)
        return 1
    return 0


def map_shapes(geometry: MapGeometry) -> dict[str, Any]:
    """The geometry as the site reads it: regions keyed by Carbon Intensity API id."""
    _, _, width, height = geometry.view_box
    x, y, frame_width, frame_height = geometry.shetland_frame
    return {
        "viewBox": {"width": width, "height": height},
        "shetlandFrame": {"x": x, "y": y, "width": frame_width, "height": frame_height},
        "regions": {
            str(region.api_id): {
                "path": geometry.regions[region.boundary_area].path,
                "labelAt": dict(
                    zip(("x", "y"), geometry.regions[region.boundary_area].label_at, strict=True)
                ),
            }
            for region in REGIONS
        },
    }


def build_map(geojson: Any) -> MapGeometry:  # parsed JSON, validated by the lookups below
    """Project a boundary FeatureCollection to SVG. Raises ValueError on a wrong CRS or shape."""
    try:
        crs_name = geojson["crs"]["properties"]["name"]
        features = list(geojson["features"])
    except (KeyError, TypeError) as err:
        raise ValueError(f"boundary file is malformed: {err!r}") from err
    if "27700" not in crs_name:
        raise ValueError(f"expected British National Grid (27700), got CRS {crs_name!r}")
    by_area: dict[str, list[Polygon]] = {}
    for position, feature in enumerate(features):
        area, polygons = _parse_feature(feature, position)
        by_area.setdefault(area, []).extend(polygons)
    unexpected = sorted(set(by_area) - _BOUNDARY_AREAS)
    if unexpected:
        raise ValueError(f"unexpected areas {unexpected}, expected only {sorted(_BOUNDARY_AREAS)}")
    missing = [region.boundary_area for region in REGIONS if not by_area.get(region.boundary_area)]
    if missing:
        raise ValueError(f"no boundary found for areas {missing}")
    return _project(by_area)


def simplify_line(points: Sequence[Point], tolerance_m: float) -> list[Point]:
    """Douglas-Peucker simplification that always keeps both end points."""
    count = len(points)
    keep = [False] * count
    keep[0] = keep[-1] = True
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        if first + 1 >= last:
            continue
        farthest, distance = max(
            (
                (i, _distance_to_chord(points[i], points[first], points[last]))
                for i in range(first + 1, last)
            ),
            key=lambda pair: pair[1],
        )
        if distance > tolerance_m:
            keep[farthest] = True
            stack.append((first, farthest))
            stack.append((farthest, last))
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def simplify_ring(ring: Ring, tolerance_m: float) -> Ring:
    """Simplify a closed ring by splitting it at the point farthest from its start."""
    if len(ring) < _MIN_RING_POINTS:
        return list(ring)
    pivot = max(range(len(ring)), key=lambda i: math.dist(ring[0], ring[i]))
    return (
        simplify_line(ring[: pivot + 1], tolerance_m) + simplify_line(ring[pivot:], tolerance_m)[1:]
    )


def ring_area(ring: Ring) -> float:
    """Absolute area of a closed ring in squared units of its coordinates."""
    return abs(_signed_area(ring))


def label_point(polygon: Polygon) -> Point:
    """A point inside the polygon: midpoint of the widest span on its centroid's latitude line."""
    exterior = polygon[0]
    area = _signed_area(exterior)
    centroid_y = sum(
        (y1 + y2) * (x1 * y2 - x2 * y1) for (x1, y1), (x2, y2) in pairwise(exterior)
    ) / (6 * area)
    crossings = sorted(
        x1 + (centroid_y - y1) * (x2 - x1) / (y2 - y1)
        for ring in polygon
        for (x1, y1), (x2, y2) in pairwise(ring)
        if (y1 <= centroid_y) != (y2 <= centroid_y)
    )
    # Even-odd rule: spans between crossing 0 and 1, 2 and 3, and so on lie inside.
    left, right = max(
        zip(crossings[0::2], crossings[1::2], strict=False), key=lambda s: s[1] - s[0]
    )
    return ((left + right) / 2, centroid_y)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gridcast-map", description="Write the site's region shapes as JSON."
    )
    parser.add_argument("boundaries", type=Path, help="region boundary GeoJSON")
    parser.add_argument("output", type=Path, help="regionShapes.json to write")
    return parser


def _parse_feature(feature: Any, position: int) -> tuple[str, list[Polygon]]:
    try:
        area = feature["properties"]["Area"]
    except (KeyError, TypeError) as err:
        raise ValueError(f"feature {position} is malformed: {err!r}") from err
    try:
        return area, _polygons_of(feature["geometry"])
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise ValueError(f"feature {position} ({area}) is malformed: {err!r}") from err


def _project(by_area: dict[str, list[Polygon]]) -> MapGeometry:
    by_area, frame_m = _shift_shetland(by_area)
    exterior_points = [p for polygons in by_area.values() for poly in polygons for p in poly[0]]
    west, south, east, north = _bounds(
        [*exterior_points, (frame_m[0], frame_m[1]), (frame_m[2], frame_m[3])]
    )
    margin = VIEW_MARGIN_M / _METRES_PER_UNIT

    def project(point: Point) -> Point:
        return (
            round((point[0] - west) / _METRES_PER_UNIT + margin, 1),
            round((north - point[1]) / _METRES_PER_UNIT + margin, 1),
        )

    left, top = project((frame_m[0], frame_m[3]))
    return MapGeometry(
        view_box=(
            0.0,
            0.0,
            round((east - west) / _METRES_PER_UNIT + 2 * margin, 1),
            round((north - south) / _METRES_PER_UNIT + 2 * margin, 1),
        ),
        shetland_frame=(
            left,
            top,
            round((frame_m[2] - frame_m[0]) / _METRES_PER_UNIT, 1),
            round((frame_m[3] - frame_m[1]) / _METRES_PER_UNIT, 1),
        ),
        regions={area: _shape(polygons, project) for area, polygons in by_area.items()},
    )


def _polygons_of(geometry: Any) -> list[Polygon]:
    kind = geometry["type"]
    if kind == "Polygon":
        raw_polygons = [geometry["coordinates"]]
    elif kind == "MultiPolygon":
        raw_polygons = geometry["coordinates"]
    else:
        raise ValueError(f"expected Polygon or MultiPolygon, got {kind!r}")
    prepared = (_prepare_polygon(raw) for raw in raw_polygons)
    return [polygon for polygon in prepared if polygon is not None]


def _prepare_polygon(raw_rings: Any) -> Polygon | None:
    exterior, *holes = (_closed_ring(raw) for raw in raw_rings)
    if ring_area(exterior) < MIN_RING_AREA_M2:
        return None
    simplified_exterior = simplify_ring(exterior, SIMPLIFY_TOLERANCE_M)
    if len(simplified_exterior) < _MIN_RING_POINTS:
        return None
    simplified_holes = (
        simplify_ring(hole, SIMPLIFY_TOLERANCE_M)
        for hole in holes
        if ring_area(hole) >= MIN_RING_AREA_M2
    )
    return [
        simplified_exterior,
        *(ring for ring in simplified_holes if len(ring) >= _MIN_RING_POINTS),
    ]


def _closed_ring(raw: Any) -> Ring:
    ring = [(float(position[0]), float(position[1])) for position in raw]
    return ring if ring[0] == ring[-1] else [*ring, ring[0]]


def _shift_shetland(
    by_area: dict[str, list[Polygon]],
) -> tuple[dict[str, list[Polygon]], tuple[float, float, float, float]]:
    """Return the areas with Shetland moved south, and its padded west, south, east, north frame."""
    moved: list[Polygon] = []
    shifted: dict[str, list[Polygon]] = {}
    for area, polygons in by_area.items():
        shifted[area] = []
        for polygon in polygons:
            if all(northing > SHETLAND_MIN_NORTHING_M for _, northing in polygon[0]):
                polygon = [
                    [(easting, northing + SHETLAND_SHIFT_NORTHING_M) for easting, northing in ring]
                    for ring in polygon
                ]
                moved.append(polygon)
            shifted[area].append(polygon)
    if not moved:
        raise ValueError(f"no polygon lies above northing {SHETLAND_MIN_NORTHING_M}")
    west, south, east, north = _bounds([p for polygon in moved for p in polygon[0]])
    pad = SHETLAND_FRAME_PADDING_M
    return shifted, (west - pad, south - pad, east + pad, north + pad)


def _bounds(points: Sequence[Point]) -> tuple[float, float, float, float]:
    eastings = [p[0] for p in points]
    northings = [p[1] for p in points]
    return (min(eastings), min(northings), max(eastings), max(northings))


def _shape(polygons: list[Polygon], project: Callable[[Point], Point]) -> RegionShape:
    projected = [[[project(p) for p in ring] for ring in polygon] for polygon in polygons]
    path = " ".join(_ring_path(ring) for polygon in projected for ring in polygon)
    largest = max(projected, key=lambda polygon: ring_area(polygon[0]))
    x, y = label_point(largest)
    return RegionShape(path=path, label_at=(round(x, 1), round(y, 1)))


def _ring_path(ring: Ring) -> str:
    points = " L ".join(f"{_number(x)} {_number(y)}" for x, y in ring[:-1])
    return f"M {points} Z"


def _number(value: float) -> str:
    text = f"{value:.1f}"
    return text.removesuffix(".0")


def _signed_area(ring: Ring) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring)) / 2


def _distance_to_chord(point: Point, start: Point, end: Point) -> float:
    chord = math.dist(start, end)
    if chord == 0:
        return math.dist(point, start)
    cross = (end[0] - start[0]) * (start[1] - point[1]) - (start[0] - point[0]) * (
        end[1] - start[1]
    )
    return abs(cross) / chord
