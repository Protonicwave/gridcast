from copy import deepcopy

import pytest
from factories import KM, all_areas, boundary_collection, shetland_like, square

from gridcast.boundaries import (
    MIN_RING_AREA_M2,
    SHETLAND_FRAME_PADDING_M,
    build_map,
    label_point,
    ring_area,
    simplify_line,
    simplify_ring,
)


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
        build_map(boundary_collection(all_areas(), crs="urn:ogc:def:crs:EPSG::4326"))


def test_rejects_malformed_file() -> None:
    with pytest.raises(ValueError, match="malformed"):
        build_map({"type": "FeatureCollection"})


def test_rejects_unsupported_geometry() -> None:
    data = boundary_collection(all_areas())
    data["features"][0]["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    with pytest.raises(ValueError, match="got 'Point'"):
        build_map(data)


def test_rejects_missing_area() -> None:
    data = boundary_collection(all_areas())
    data["features"].pop()
    with pytest.raises(ValueError, match="no boundary found"):
        build_map(data)


def test_rejects_area_that_is_not_a_region() -> None:
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    data["features"].append(deepcopy(data["features"][0]))
    data["features"][-1]["properties"]["Area"] = "Atlantis"
    with pytest.raises(ValueError, match=r"unexpected areas .*Atlantis"):
        build_map(data)


def test_rejects_area_whose_islands_are_all_too_small() -> None:
    placements = all_areas(**{"North_Scotland": [shetland_like()]})
    placements["London"] = [square(10_000.0, 10_000.0, (MIN_RING_AREA_M2**0.5) * 0.9)]
    with pytest.raises(ValueError, match=r"no boundary found for areas \['London'\]"):
        build_map(boundary_collection(placements))


def test_rejects_unreadable_coordinate_naming_the_feature() -> None:
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    data["features"][2]["geometry"]["coordinates"][0][0][1] = ["x", 5]
    with pytest.raises(ValueError, match=r"feature 2 \(North West England\)"):
        build_map(data)


def test_rejects_missing_coordinates_naming_the_feature() -> None:
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    data["features"][3]["geometry"]["coordinates"][0] = []
    with pytest.raises(ValueError, match=r"feature 3 \(North East England\)"):
        build_map(data)


def test_accepts_polygon_geometry_like_a_single_part_multipolygon() -> None:
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    expected = build_map(data)
    feature = data["features"][12]
    assert feature["properties"]["Area"] == "London"
    feature["geometry"] = {"type": "Polygon", "coordinates": feature["geometry"]["coordinates"][0]}
    assert build_map(data) == expected


def test_rejects_file_without_shetland() -> None:
    with pytest.raises(ValueError, match="no polygon lies above northing"):
        build_map(boundary_collection(all_areas()))


def test_drops_islands_below_the_minimum_area() -> None:
    small_side = (MIN_RING_AREA_M2**0.5) * 0.9
    tiny = square(10_000.0, 10_000.0, small_side)
    kept_alone = build_map(boundary_collection(all_areas(Yorkshire=[shetland_like()])))
    with_island = build_map(boundary_collection(all_areas(Yorkshire=[shetland_like(), tiny])))
    assert with_island.regions["Yorkshire"] == kept_alone.regions["Yorkshire"]
    assert with_island.view_box == kept_alone.view_box


def test_keeps_islands_above_the_minimum_area() -> None:
    big_side = (MIN_RING_AREA_M2**0.5) * 1.1
    island = square(10_000.0, 10_000.0, big_side)
    base = build_map(boundary_collection(all_areas(Yorkshire=[shetland_like()])))
    bigger = build_map(boundary_collection(all_areas(Yorkshire=[shetland_like(), island])))
    assert (
        bigger.regions["Yorkshire"].path.count("M") == base.regions["Yorkshire"].path.count("M") + 1
    )


def test_shifts_shetland_and_frames_it() -> None:
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    geometry = build_map(data)
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
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    geometry = build_map(data)
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
    data = boundary_collection(all_areas(**{"North_Scotland": [shetland_like()]}))
    path = build_map(data).regions["London"].path
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


def test_ring_area_is_absolute_whichever_way_the_ring_runs() -> None:
    anticlockwise = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    assert ring_area(anticlockwise) == 100.0
    assert ring_area(anticlockwise[::-1]) == 100.0
