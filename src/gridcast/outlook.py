"""A region's cleanest and dirtiest windows among the half hours still ahead."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from gridcast.forecast import SLOT_MINUTES
from gridcast.issues import StoredIssue
from gridcast.regions import Region
from gridcast.windows import Window, cleanest_window, dirtiest_window, timing_matters

DURATIONS_HOURS = (1, 2, 3, 4)
_SLOTS_PER_HOUR = 60 // SLOT_MINUTES


@dataclass(frozen=True, slots=True)
class DurationWindows:
    """The windows of one duration. Window starts index into `Outlook.intensities`."""

    cleanest: Window
    dirtiest: Window
    timing_matters: bool


@dataclass(frozen=True, slots=True)
class Outlook:
    """What a region's page shows: the forecast from the current half hour, with windows.

    A duration is absent from `windows` when fewer half hours remain than it needs.
    """

    region: Region
    fetched_at: datetime
    first_slot_start: datetime
    intensities_g_per_kwh: tuple[int, ...]
    windows: dict[int, DurationWindows]


def build_outlook(region: Region, issue: StoredIssue, now: datetime) -> Outlook | None:
    """The outlook from the half hour containing `now`, or None if the issue has none left.

    Half hours that ended at or before `now` are dropped, so no window starts in the past.
    `now` must be timezone-aware.
    """
    slot_length = timedelta(minutes=SLOT_MINUTES)
    elapsed_slots = max(0, (now - issue.first_slot) // slot_length)
    remaining = issue.intensities_g_per_kwh[elapsed_slots:]
    if not remaining:
        return None
    windows: dict[int, DurationWindows] = {}
    for hours in DURATIONS_HOURS:
        slots = hours * _SLOTS_PER_HOUR
        if len(remaining) < slots:
            continue
        cleanest = cleanest_window(remaining, slots)
        dirtiest = dirtiest_window(remaining, slots)
        windows[hours] = DurationWindows(cleanest, dirtiest, timing_matters(cleanest, dirtiest))
    return Outlook(
        region=region,
        fetched_at=issue.fetched_at,
        first_slot_start=issue.first_slot + elapsed_slots * slot_length,
        intensities_g_per_kwh=remaining,
        windows=windows,
    )
