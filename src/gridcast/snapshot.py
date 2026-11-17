"""Build mockup/snapshot.js from the saved forecast, region boundaries and pilot results."""

import argparse
import json
import math
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from gridcast.boundaries import MapGeometry, build_map
from gridcast.forecast import (
    FUELS,
    SLOT_MINUTES,
    RegionalForecast,
    format_slot_time,
    parse_forecast,
    parse_slot_time,
)
from gridcast.regions import REGIONS, Region
from gridcast.windows import cleanest_window, dirtiest_window, timing_matters

MAX_INPUT_BYTES = 20 * 1024 * 1024
DURATIONS_HOURS = (1, 2, 3, 4)
ILLUSTRATIVE_MAE_NOW_G_PER_KWH = 6.0
ILLUSTRATIVE_MAE_48H_G_PER_KWH = 14.0

_SLOTS_PER_HOUR = 60 // SLOT_MINUTES
_ILLUSTRATIVE_HORIZON_HOURS = 48.0
# Normal 10th and 90th percentile multiplier, and the ratio of standard deviation to mean
# absolute error for a normal distribution.
_Z_P90 = 1.2816
_SIGMA_PER_MAE = math.sqrt(math.pi / 2)
_PILOT_DECIMAL_PLACES = 3


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point. Returns the process exit status."""
    args = _parser().parse_args(argv)
    try:
        fetched_at = parse_slot_time(args.fetched_at)
        forecast = parse_forecast(_read_json(args.forecast))
        geometry = build_map(_read_json(args.boundaries))
        snapshot = build_snapshot(forecast, geometry, _read_json(args.pilot), fetched_at)
        args.output.write_text(
            "window.GRIDCAST_SNAPSHOT = "
            + json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
            + ";\n",
            encoding="utf-8",
            newline="\n",
        )
    except (OSError, ValueError) as err:
        print(f"gridcast-snapshot: {err}", file=sys.stderr)
        return 1
    return 0


def build_snapshot(
    forecast: RegionalForecast,
    geometry: MapGeometry,
    pilot: Any,  # parsed JSON, validated by _pilot_summary
    fetched_at: datetime,
) -> dict[str, Any]:
    """Assemble the page data. Raises ValueError if fetched_at is outside the first slot."""
    first_start = forecast.slot_starts[0]
    if not first_start <= fetched_at < first_start + timedelta(minutes=SLOT_MINUTES):
        raise ValueError(
            f"fetched-at {format_slot_time(fetched_at)} is not inside the first slot "
            f"starting {format_slot_time(first_start)}"
        )
    return {
        "fetchedAt": format_slot_time(fetched_at),
        "firstSlotStart": format_slot_time(first_start),
        "slotMinutes": SLOT_MINUTES,
        "fuels": list(FUELS),
        "viewBox": list(geometry.view_box),
        "shetlandFrame": list(geometry.shetland_frame),
        "durationsHours": list(DURATIONS_HOURS),
        "regions": [_region_entry(region, forecast, geometry, fetched_at) for region in REGIONS],
        "pilot": _pilot_summary(pilot),
    }


def illustrative_range(
    values: Sequence[int], slot_starts: Sequence[datetime], fetched_at: datetime
) -> tuple[list[float], list[float]]:
    """Placeholder for the mock-up: a made-up 10th to 90th percentile band, not a model output."""
    low: list[float] = []
    high: list[float] = []
    for value, start in zip(values, slot_starts, strict=True):
        midpoint = start + timedelta(minutes=SLOT_MINUTES / 2)
        hours_ahead = (midpoint - fetched_at).total_seconds() / 3600
        hours_ahead = min(max(hours_ahead, 0.0), _ILLUSTRATIVE_HORIZON_HOURS)
        mae = ILLUSTRATIVE_MAE_NOW_G_PER_KWH + (
            ILLUSTRATIVE_MAE_48H_G_PER_KWH - ILLUSTRATIVE_MAE_NOW_G_PER_KWH
        ) * (hours_ahead / _ILLUSTRATIVE_HORIZON_HOURS)
        half_width = _Z_P90 * _SIGMA_PER_MAE * mae
        low.append(round(max(0.0, value - half_width), 1))
        high.append(round(value + half_width, 1))
    return low, high


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gridcast-snapshot", description="Write the mock-up's snapshot.js."
    )
    parser.add_argument(
        "--fetched-at", required=True, help='UTC time the forecast was fetched, "YYYY-MM-DDTHH:MMZ"'
    )
    parser.add_argument("forecast", type=Path, help="regional fw48h forecast JSON")
    parser.add_argument("boundaries", type=Path, help="region boundary GeoJSON")
    parser.add_argument("pilot", type=Path, help="pilot results JSON")
    parser.add_argument("output", type=Path, help="snapshot.js to write")
    return parser


def _read_json(path: Path) -> Any:  # the caller validates the parsed document
    with path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"{path} is larger than {MAX_INPUT_BYTES} bytes")
    try:
        return json.loads(raw)
    except RecursionError as err:
        raise ValueError(f"{path} is nested too deeply to parse") from err


def _region_entry(
    region: Region, forecast: RegionalForecast, geometry: MapGeometry, fetched_at: datetime
) -> dict[str, Any]:
    series = forecast.series[region.api_id]
    longest_slots = max(DURATIONS_HOURS) * _SLOTS_PER_HOUR
    if len(series.forecast) < longest_slots:
        raise ValueError(
            f"region {region.name}: forecast has {len(series.forecast)} slots, "
            f"fewer than the {longest_slots} slots ({max(DURATIONS_HOURS)}-hour window) needed"
        )
    shape = geometry.regions[region.boundary_area]
    low, high = illustrative_range(series.forecast, forecast.slot_starts, fetched_at)
    return {
        "id": region.api_id,
        "name": region.name,
        "path": shape.path,
        "labelAt": list(shape.label_at),
        "forecast": list(series.forecast),
        "index": list(series.index),
        "mix": [list(slot_mix) for slot_mix in series.mix],
        "windows": {str(hours): _windows_for(series.forecast, hours) for hours in DURATIONS_HOURS},
        "illustrativeRange": {"low": low, "high": high},
    }


def _windows_for(values: Sequence[int], hours: int) -> dict[str, Any]:
    # Slot 0 is searched although it began before the fetch: the current half hour is still
    # usable, and the page calls a window that starts there "now".
    cleanest = cleanest_window(values, hours * _SLOTS_PER_HOUR)
    dirtiest = dirtiest_window(values, hours * _SLOTS_PER_HOUR)
    return {
        "cleanest": {"start": cleanest.start, "mean": round(cleanest.mean, 1)},
        "dirtiest": {"start": dirtiest.start, "mean": round(dirtiest.mean, 1)},
        "timingMatters": timing_matters(cleanest, dirtiest),
    }


def _pilot_summary(pilot: Any) -> dict[str, Any]:
    count = _pilot_field(pilot, "errors", "n")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"pilot file: errors.n expected a positive integer, got {count!r:.80}")
    threshold = _pilot_number(pilot, "window_pilot", "regret_threshold")
    if not 0 <= threshold <= 1:
        raise ValueError(
            f"pilot file: window_pilot.regret_threshold expected 0 to 1, got {threshold}"
        )
    return {
        "n": count,
        "mae": _pilot_rounded(pilot, "errors", "mae"),
        "maeLow": _pilot_rounded(pilot, "errors", "mae_ci95_low"),
        "maeHigh": _pilot_rounded(pilot, "errors", "mae_ci95_high"),
        "p95AbsoluteError": _pilot_rounded(pilot, "errors", "p95_absolute_error"),
        "maeByHourUtc": [_pilot_rounded(pilot, "mae_by_hour_utc", str(hour)) for hour in range(24)],
        "windowHours": _pilot_number(pilot, "window_pilot", "window_hours"),
        "regretThreshold": threshold,
        "shareWithinThreshold": _pilot_rounded(
            pilot, "window_pilot", "share_regret_at_most_threshold"
        ),
        "shareExactBest": _pilot_rounded(pilot, "window_pilot", "share_windows_coincide"),
    }


def _pilot_field(pilot: Any, *path: str) -> Any:
    value = pilot
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"pilot file: missing field {'.'.join(path)}")
        value = value[key]
    return value


def _pilot_number(pilot: Any, *path: str) -> float:
    value = _pilot_field(pilot, *path)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(
            f"pilot file: {'.'.join(path)} expected a finite number, got {value!r:.80}"
        )
    return value


def _pilot_rounded(pilot: Any, *path: str) -> float:
    return round(_pilot_number(pilot, *path), _PILOT_DECIMAL_PLACES)
