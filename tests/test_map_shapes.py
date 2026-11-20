import json
from pathlib import Path
from typing import Any

import pytest
from factories import all_areas, boundary_collection, shetland_like

from gridcast.boundaries import build_map, main
from gridcast.regions import REGIONS

REPO_ROOT = Path(__file__).resolve().parent.parent
BOUNDARIES = REPO_ROOT / "data" / "gb-dno-license-areas-20240503.geojson"
COMMITTED_SHAPES = REPO_ROOT / "web" / "src" / "map" / "regionShapes.json"


def _write_boundaries(directory: Path) -> Path:
    path = directory / "boundaries.geojson"
    path.write_text(
        json.dumps(boundary_collection(all_areas(North_Scotland=[shetland_like()]))),
        encoding="utf-8",
    )
    return path


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_writes_every_region_keyed_by_its_api_id(tmp_path: Path) -> None:
    output = tmp_path / "shapes.json"
    assert main([str(_write_boundaries(tmp_path)), str(output)]) == 0
    shapes = _load(output)
    geometry = build_map(boundary_collection(all_areas(North_Scotland=[shetland_like()])))
    assert list(shapes["regions"]) == [str(region.api_id) for region in REGIONS]
    for region in REGIONS:
        shape = geometry.regions[region.boundary_area]
        assert shapes["regions"][str(region.api_id)] == {
            "path": shape.path,
            "labelAt": {"x": shape.label_at[0], "y": shape.label_at[1]},
        }


def test_writes_the_view_box_and_the_shetland_frame(tmp_path: Path) -> None:
    output = tmp_path / "shapes.json"
    main([str(_write_boundaries(tmp_path)), str(output)])
    shapes = _load(output)
    geometry = build_map(boundary_collection(all_areas(North_Scotland=[shetland_like()])))
    assert geometry.view_box[:2] == (0.0, 0.0)
    assert shapes["viewBox"] == {"width": geometry.view_box[2], "height": geometry.view_box[3]}
    x, y, width, height = geometry.shetland_frame
    assert shapes["shetlandFrame"] == {"x": x, "y": y, "width": width, "height": height}


def test_output_is_compact_utf8_with_a_unix_newline(tmp_path: Path) -> None:
    output = tmp_path / "shapes.json"
    main([str(_write_boundaries(tmp_path)), str(output)])
    raw = output.read_bytes()
    assert raw.endswith(b"}\n")
    assert b"\r" not in raw
    assert b": " not in raw


def test_reports_a_missing_boundary_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "absent.geojson"), str(tmp_path / "shapes.json")]) == 1
    assert "absent.geojson" in capsys.readouterr().err


def test_reports_a_boundary_file_that_is_not_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.geojson"
    broken.write_text("{", encoding="utf-8")
    assert main([str(broken), str(tmp_path / "shapes.json")]) == 1
    assert "broken.geojson" in capsys.readouterr().err


def test_reports_a_boundary_file_the_map_rejects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rejected = tmp_path / "rejected.geojson"
    rejected.write_text(json.dumps({"type": "FeatureCollection"}), encoding="utf-8")
    assert main([str(rejected), str(tmp_path / "shapes.json")]) == 1
    assert "malformed" in capsys.readouterr().err


def test_the_committed_shapes_are_what_the_tool_writes_for_the_boundary_data(
    tmp_path: Path,
) -> None:
    output = tmp_path / "shapes.json"
    assert main([str(BOUNDARIES), str(output)]) == 0
    # Text mode, so a checkout that converts line endings does not fail the comparison.
    assert COMMITTED_SHAPES.read_text(encoding="utf-8") == output.read_text(encoding="utf-8")
