from typing import Any

import pytest

from gridcast.boundaries import (
    MIN_RING_AREA_M2,
    SHETLAND_FRAME_PADDING_M,
    build_map,
    label_point,
    ring_area,
    simplify_line,
    simplify_ring,
)
from gridcast.regions import REGIONS

KM = 1000.0


def _square(west: float, south: float, side_m: float) -> list[list[float]]:
    east, north = west + side_m, south + side_m
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def _collection(
    placements: dict[str, list[list[list[float]]]], crs: str = "urn:ogc:def:crs:EPSG::27700"
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


def _all_areas(**extra: list[list[list[float]]]) -> dict[str, list[list[list[float]]]]:
    """Every area as a 40 km square on a diagonal, plus any extra rings for named areas."""
    placements = {
        region.boundary_area: [_square(50_000 * region.api_id, 50_000 * region.api_id, 40 * KM)]
        for region in REGIONS
    }
    for area, rings in extra.items():
        placements[area.replace("_", " ")] += rings
    return placements


def test_simplify_line_keeps_end_points_and_drops_collinear_points() -> None:
    line = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]
    assert simplify_line(line, 1.0) == [(0.0, 0.0), (4.0, 0.0)]


def test_simplify_line_keeps_a_point_beyond_the_tolerance() -> None:
    line = [(0.0, 0.0), (2.0, 5.0), (4.0, 0.0)]
    assert simplify_line(line, 1.0) == line


def test_simplify_line_drops_a_point_within_the_tolerance() -> None:
    line = [(0.0, 0.0), (2.0, 0.5), (4.0, 0.0)]
    assert simplify_line(line, 1.0) == [(0.0, 0.0), (4.0, 0.0)]


def test_simplify_line_copes_with_a_zero_length_chord() -> None:
    line = [(0.0, 0.0), (3.0, 0.0), (0.0, 0.0)]
    assert simplify_line(line, 1.0) == line


def test_simplify_ring_keeps_corners_and_closes_the_ring() -> None:
    ring = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    simplified = simplify_ring(ring, 1.0)
    assert simplified[0] == simplified[-1] == (0.0, 0.0)
    assert (5.0, 0.0) not in simplified
    assert {(10.0, 0.0), (10.0, 10.0), (0.0, 10.0)} <= set(simplified)


def test_simplify_ring_leaves_a_tiny_ring_alone() -> None:
    ring = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)]
    assert simplify_ring(ring, 10.0) == ring


def test_rejects_other_coordinate_reference_system() -> None:
    with pytest.raises(ValueError, match="EPSG::4326"):
        build_map(_collection(_all_areas(), crs="urn:ogc:def:crs:EPSG::4326"))


def test_rejects_malformed_file() -> None:
    with pytest.raises(ValueError, match="malformed"):
        build_map({"type": "FeatureCollection"})


def test_rejects_unsupported_geometry() -> None:
    data = _collection(_all_areas())
    data["features"][0]["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    with pytest.raises(ValueError, match="got 'Point'"):
        build_map(data)


def test_rejects_missing_area() -> None:
    data = _collection(_all_areas())
    data["features"].pop()
    with pytest.raises(ValueError, match="no boundary found"):
        build_map(data)


def test_rejects_file_without_shetland() -> None:
    with pytest.raises(ValueError, match="no polygon lies above northing"):
        build_map(_collection(_all_areas()))


def _shetland_like(west: float = 450_000.0) -> list[list[float]]:
    return _square(west, 1_150_000.0, 30 * KM)


def test_drops_islands_below_the_minimum_area() -> None:
    small_side = (MIN_RING_AREA_M2**0.5) * 0.9
    tiny = _square(10_000.0, 10_000.0, small_side)
    kept_alone = build_map(_collection(_all_areas(Yorkshire=[_shetland_like()])), tolerance_m=100.0)
    with_island = build_map(
        _collection(_all_areas(Yorkshire=[_shetland_like(), tiny])), tolerance_m=100.0
    )
    assert with_island.regions["Yorkshire"] == kept_alone.regions["Yorkshire"]
    assert with_island.view_box == kept_alone.view_box


def test_keeps_islands_above_the_minimum_area() -> None:
    big_side = (MIN_RING_AREA_M2**0.5) * 1.1
    island = _square(10_000.0, 10_000.0, big_side)
    base = build_map(_collection(_all_areas(Yorkshire=[_shetland_like()])), tolerance_m=100.0)
    bigger = build_map(
        _collection(_all_areas(Yorkshire=[_shetland_like(), island])), tolerance_m=100.0
    )
    assert (
        bigger.regions["Yorkshire"].path.count("M") == base.regions["Yorkshire"].path.count("M") + 1
    )


def test_shifts_shetland_and_frames_it() -> None:
    data = _collection(_all_areas(**{"North_Scotland": [_shetland_like()]}))
    geometry = build_map(data, tolerance_m=100.0)
    pad_units = SHETLAND_FRAME_PADDING_M / KM
    left, top, width, height = geometry.shetland_frame
    assert width == pytest.approx(30 + 2 * pad_units, abs=0.2)
    assert height == pytest.approx(30 + 2 * pad_units, abs=0.2)
    view_left, view_top, view_width, view_height = geometry.view_box
    assert view_left == view_top == 0
    assert left >= 0
    assert top >= 0
    assert left + width <= view_width
    assert top + height <= view_height
    # Unshifted, Shetland would reach 1,180 km northing and the map would exceed 1,100 km.
    assert view_height < 1_000


def test_view_box_has_margin_on_every_side() -> None:
    data = _collection(_all_areas(**{"North_Scotland": [_shetland_like()]}))
    geometry = build_map(data, tolerance_m=100.0)
    xs: list[float] = []
    ys: list[float] = []
    for shape in geometry.regions.values():
        numbers = [
            float(token)
            for token in shape.path.replace("M", " ").replace("L", " ").replace("Z", " ").split()
        ]
        xs += numbers[0::2]
        ys += numbers[1::2]
    _, _, width, height = geometry.view_box
    assert min(xs) >= 5.0
    assert min(ys) >= 5.0
    assert max(xs) <= width - 5.0
    assert max(ys) <= height - 5.0


def test_path_is_closed_move_line_form() -> None:
    data = _collection(_all_areas(**{"North_Scotland": [_shetland_like()]}))
    path = build_map(data, tolerance_m=100.0).regions["London"].path
    assert path.startswith("M ")
    assert path.endswith(" Z")
    assert path.count("M") == 1
    assert " L " in path


def test_label_point_of_a_u_shaped_polygon_lies_inside() -> None:
    # A U opening upwards: centroid sits in the gap's height band, so a naive centroid is outside.
    u_shape = [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 10.0),
        (7.0, 10.0),
        (7.0, 2.0),
        (3.0, 2.0),
        (3.0, 10.0),
        (0.0, 10.0),
        (0.0, 0.0),
    ]
    x, y = label_point([u_shape])
    assert not 3.0 < x < 7.0
    assert 0.0 < x < 10.0
    assert 0.0 < y < 10.0


def test_label_point_avoids_a_hole() -> None:
    outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    hole = [(1.0, 4.0), (9.0, 4.0), (9.0, 6.0), (1.0, 6.0), (1.0, 4.0)]
    x, y = label_point([outer, hole])
    assert not (1.0 < x < 9.0 and 4.0 < y < 6.0)
    assert ring_area(outer) == 100.0
