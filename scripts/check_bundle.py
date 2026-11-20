"""Checks the built site's script against its size budgets.

Usage: python scripts/check_bundle.py web/dist

Reads the manifest Vite writes beside the build, gzips each script chunk as a server would
send it, and compares the entry chunk, each lazily loaded chunk that has a budget, and all
script together with their limits. Prints one line per check. Exits 0 when every figure is
within its budget, 1 when one is over or a chunk with a budget is missing, and 2 when the
build cannot be read.
"""

import argparse
import gzip
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

KIB = 1024
# The level servers and Vite's own report use by default.
GZIP_LEVEL = 6
ENTRY_BUDGET_KIB = 80
TOTAL_BUDGET_KIB = 110
# Lazily loaded chunks by the source file Vite names in its manifest.
CHUNK_BUDGETS_KIB = {"src/map/RegionMap.tsx": 16, "src/accuracy/AccuracyView.tsx": 10}
EXIT_OVER_BUDGET = 1
EXIT_UNREADABLE = 2


class UnreadableBuildError(Exception):
    """The build's manifest or a chunk it lists could not be read."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dist", type=Path, help="the build folder, for example web/dist")
    dist: Path = parser.parse_args(argv).dist
    try:
        manifest = _read_manifest(dist)
        entry_keys = [key for key, chunk in manifest.items() if chunk.get("isEntry")]
        if len(entry_keys) != 1:
            raise UnreadableBuildError(
                f"expected one entry chunk in the manifest, got {len(entry_keys)}"
            )
        sizes = {
            key: _gzipped_kib(dist, chunk) for key, chunk in manifest.items() if _is_script(chunk)
        }
    except UnreadableBuildError as err:
        print(f"check_bundle: {err}", file=sys.stderr)
        return EXIT_UNREADABLE
    checks = [
        ("entry", sizes[entry_keys[0]], ENTRY_BUDGET_KIB),
        *((source, sizes.get(source), budget) for source, budget in CHUNK_BUDGETS_KIB.items()),
        ("total", sum(sizes.values()), TOTAL_BUDGET_KIB),
    ]
    lines = [_report_line(label, kib, budget) for label, kib, budget in checks]
    print("\n".join(lines))
    return 0 if all(": ok, " in line for line in lines) else EXIT_OVER_BUDGET


def _read_manifest(dist: Path) -> Mapping[str, Mapping[str, Any]]:
    path = dist / ".vite" / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise UnreadableBuildError(f"cannot read {path}: {err}") from err
    if not isinstance(manifest, dict):
        raise UnreadableBuildError(
            f"expected {path} to hold an object, got {type(manifest).__name__}"
        )
    return manifest


def _is_script(chunk: Mapping[str, Any]) -> bool:
    return str(chunk.get("file", "")).endswith(".js")


def _gzipped_kib(dist: Path, chunk: Mapping[str, Any]) -> float:
    path = dist / str(chunk["file"])
    try:
        compressed = gzip.compress(path.read_bytes(), compresslevel=GZIP_LEVEL, mtime=0)
    except OSError as err:
        raise UnreadableBuildError(f"cannot read {path}: {err}") from err
    return len(compressed) / KIB


def _report_line(label: str, kib: float | None, budget_kib: int) -> str:
    if kib is None:
        return f"{label}: missing, expected a chunk with a budget of {budget_kib} KiB"
    status = "ok" if kib <= budget_kib else "over"
    return f"{label}: {status}, {kib:.1f} KiB of {budget_kib} KiB"


if __name__ == "__main__":
    sys.exit(main())
