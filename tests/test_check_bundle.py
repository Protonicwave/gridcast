import gzip
import importlib.util
import json
import random
import re
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_bundle.py"
KIB = 1024
MAP_SOURCE = "src/map/RegionMap.tsx"
ACCURACY_SOURCE = "src/accuracy/AccuracyView.tsx"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_bundle", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_bundle = _load_script()


def _incompressible(size_bytes: int) -> bytes:
    """Bytes that gzip cannot shrink, so a chunk's compressed size is close to this."""
    # Seeded for repeatable sizes; the bytes protect nothing.
    return random.Random(size_bytes).randbytes(size_bytes)  # noqa: S311


def _write_dist(
    dist: Path,
    *,
    entry_bytes: int = 10 * KIB,
    map_bytes: int | None = 5 * KIB,
    accuracy_bytes: int | None = 3 * KIB,
    shared_bytes: int | None = None,
) -> None:
    (dist / ".vite").mkdir(parents=True)
    (dist / "assets").mkdir()
    manifest: dict[str, dict[str, object]] = {
        "index.html": {"file": "assets/index.js", "src": "index.html", "isEntry": True}
    }
    (dist / "assets" / "index.js").write_bytes(_incompressible(entry_bytes))
    if map_bytes is not None:
        manifest[MAP_SOURCE] = {
            "file": "assets/map.js",
            "src": MAP_SOURCE,
            "isDynamicEntry": True,
        }
        (dist / "assets" / "map.js").write_bytes(_incompressible(map_bytes))
    if accuracy_bytes is not None:
        manifest[ACCURACY_SOURCE] = {
            "file": "assets/accuracy.js",
            "src": ACCURACY_SOURCE,
            "isDynamicEntry": True,
        }
        (dist / "assets" / "accuracy.js").write_bytes(_incompressible(accuracy_bytes))
    if shared_bytes is not None:
        manifest["_shared.js"] = {"file": "assets/shared.js", "name": "shared"}
        (dist / "assets" / "shared.js").write_bytes(_incompressible(shared_bytes))
    (dist / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _run(dist: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    status: int = check_bundle.main([str(dist)])
    return status, capsys.readouterr().out


def test_passes_when_every_chunk_is_within_its_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path)
    status, report = _run(tmp_path, capsys)
    assert status == 0
    assert "entry: ok, " in report
    assert f"{MAP_SOURCE}: ok, " in report
    assert "total: ok, " in report


def test_fails_when_the_entry_is_over_its_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path, entry_bytes=81 * KIB)
    status, report = _run(tmp_path, capsys)
    assert status == 1
    assert "entry: over, " in report


def test_fails_when_the_map_chunk_is_over_its_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path, map_bytes=17 * KIB)
    status, report = _run(tmp_path, capsys)
    assert status == 1
    assert f"{MAP_SOURCE}: over, " in report


def test_fails_when_all_the_script_together_is_over_its_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Each chunk is within its own budget, and a shared chunk has none of its own.
    _write_dist(tmp_path, entry_bytes=60 * KIB, map_bytes=15 * KIB, shared_bytes=40 * KIB)
    status, report = _run(tmp_path, capsys)
    assert status == 1
    assert "total: over, " in report


def test_counts_a_chunk_with_no_budget_of_its_own_in_the_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path, shared_bytes=20 * KIB)
    _, report = _run(tmp_path, capsys)
    match = re.search(r"total: ok, ([\d.]+) KiB", report)
    assert match is not None
    # 10 + 5 + 3 + 20 KiB of bytes gzip cannot shrink, plus its small framing.
    assert 38.0 <= float(match.group(1)) <= 38.5


def test_fails_when_a_budgeted_chunk_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path, map_bytes=None)
    status, report = _run(tmp_path, capsys)
    assert status == 1
    assert f"{MAP_SOURCE}: missing" in report


def test_measures_the_gzipped_size_not_the_raw_size(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path)
    (tmp_path / "assets" / "index.js").write_bytes(b"a" * (200 * KIB))
    status, _ = _run(tmp_path, capsys)
    assert status == 0
    assert len(gzip.compress(b"a" * (200 * KIB))) < KIB


def test_reports_a_dist_without_a_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = check_bundle.main([str(tmp_path)])
    assert status == 2
    assert "manifest.json" in capsys.readouterr().err


def test_reports_a_manifest_that_is_not_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".vite").mkdir()
    (tmp_path / ".vite" / "manifest.json").write_text("{", encoding="utf-8")
    assert check_bundle.main([str(tmp_path)]) == 2
    assert "manifest.json" in capsys.readouterr().err


def test_reports_a_manifest_without_an_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".vite").mkdir()
    (tmp_path / ".vite" / "manifest.json").write_text("{}", encoding="utf-8")
    assert check_bundle.main([str(tmp_path)]) == 2
    assert "entry" in capsys.readouterr().err


def test_reports_a_listed_chunk_that_is_not_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_dist(tmp_path)
    (tmp_path / "assets" / "index.js").unlink()
    assert check_bundle.main([str(tmp_path)]) == 2
    assert "index.js" in capsys.readouterr().err
