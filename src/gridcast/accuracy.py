"""NESO's national forecast error by lead time, with a bootstrap interval per band.

A forecast is compared with the measured intensity of each half hour it covers. The
lead time is the slot's start minus the time the forecast was fetched, which is what
a user of the API had in hand.
"""

import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from gridcast.forecast import SLOT_MINUTES
from gridcast.issues import StoredIssue

SLOTS_PER_DAY = 48
# The forecast is fetched every half hour, so a slot is forecast twice per hour of lead time.
NOMINAL_PAIRS_PER_BAND_HOUR_PER_SLOT = 2
MIN_BAND_SHARE = 0.9
MIN_DAYS_FOR_INTERVAL = 7
MAX_DAYS_EVALUATED = 120
RESAMPLES = 2_000
SEED = 20_261_117
# With n=40 the cut points fall every 2.5%: the first is the 2.5th percentile and the
# last, the 39th, the 97.5th.
INTERVAL_CUT_POINTS = 40

_SLOT_SECONDS = SLOT_MINUTES * 60
_DAY_SECONDS = 86_400
_HOUR_SECONDS = 3_600
_MAX_HORIZON_HOURS = 48
# A forecast for a day can be fetched up to this long before it starts.
MAX_LEAD_TIME = timedelta(hours=_MAX_HORIZON_HOURS)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Band:
    """Lead times from `start_hours` up to `end_hours`; the last band includes its end."""

    start_hours: int
    end_hours: int

    @property
    def hours(self) -> int:
        return self.end_hours - self.start_hours

    @property
    def label(self) -> str:
        return f"{self.start_hours} to {self.end_hours} h"


BANDS = (Band(1, 6), Band(6, 12), Band(12, 24), Band(24, _MAX_HORIZON_HOURS))
_LAST_BAND = len(BANDS) - 1


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class Estimate:
    """A mean absolute error in g/kWh, and its 95% interval once there are enough days.

    `mae_g_per_kwh` is None when no day is usable. For the difference it is the long
    band's error minus the short band's.
    """

    mae_g_per_kwh: float | None
    interval: Interval | None


@dataclass(frozen=True, slots=True)
class BandAccuracy:
    band: Band
    pairs: int
    estimate: Estimate


@dataclass(frozen=True, slots=True)
class ExcludedDay:
    day: date
    reason: str


@dataclass(frozen=True, slots=True)
class NationalAccuracy:
    """Error per band over the usable days, and the long band minus the short band."""

    bands: tuple[BandAccuracy, ...]
    difference: Estimate
    usable_days: tuple[date, ...]
    excluded_days: tuple[ExcludedDay, ...]


@dataclass(slots=True)
class _DayTally:
    abs_error_sums: list[int] = field(default_factory=lambda: [0] * len(BANDS))
    pairs: list[int] = field(default_factory=lambda: [0] * len(BANDS))


def horizon_band(issued_at: datetime, slot_start: datetime) -> Band | None:
    """The band the lead time from `issued_at` to `slot_start` falls in, or None.

    Under one hour, over 48 hours and negative lead times are in no band.
    """
    position = _band_position(int((slot_start - issued_at).total_seconds()))
    return None if position is None else BANDS[position]


def evaluation_window(today: date, until: date | None = None) -> tuple[date, date]:
    """The first UTC day evaluated and the day the evaluation stops before.

    The window ends at `until` or `today`, whichever is earlier, so a day still under
    way is never read, and spans at most MAX_DAYS_EVALUATED days.
    """
    end = today if until is None else min(until, today)
    return end - timedelta(days=MAX_DAYS_EVALUATED), end


def evaluate_national(
    issues: Iterable[StoredIssue],
    actuals: Mapping[datetime, int],
    today: date,
    until: date | None = None,
) -> NationalAccuracy:
    """Error of `issues` against `actuals` for the UTC days before `until` and `today`.

    At most the MAX_DAYS_EVALUATED days before the earlier of the two are read. A day
    is used only when all its half hours have an actual and every band holds enough
    pairs; the others are listed with the reason.
    """
    start, end = evaluation_window(today, until)
    actual_by_epoch = {int(slot.timestamp()): value for slot, value in actuals.items()}
    tallies = _tally_pairs(issues, actual_by_epoch, start, end)
    actuals_per_day = _count_actuals_per_day(actual_by_epoch, start, end)
    usable: dict[date, _DayTally] = {}
    excluded: list[ExcludedDay] = []
    for day in sorted(tallies.keys() | actuals_per_day.keys()):
        tally = tallies.get(day, _DayTally())
        reason = _unusable_reason(actuals_per_day.get(day, 0), tally)
        if reason is None:
            usable[day] = tally
        else:
            excluded.append(ExcludedDay(day, reason))
    return _summarise(usable, tuple(excluded))


def _band_position(horizon_seconds: int) -> int | None:
    for position, band in enumerate(BANDS):
        within = (
            band.start_hours * _HOUR_SECONDS <= horizon_seconds < band.end_hours * _HOUR_SECONDS
        )
        at_the_end = position == _LAST_BAND and horizon_seconds == band.end_hours * _HOUR_SECONDS
        if within or at_the_end:
            return position
    return None


def _day_of(epoch_seconds: int) -> date:
    return (_EPOCH + timedelta(seconds=epoch_seconds - epoch_seconds % _DAY_SECONDS)).date()


def _tally_pairs(
    issues: Iterable[StoredIssue], actual_by_epoch: Mapping[int, int], start: date, end: date
) -> dict[date, _DayTally]:
    start_epoch = _epoch_of(start)
    end_epoch = _epoch_of(end)
    tallies: dict[date, _DayTally] = {}
    for issue in issues:
        issued_epoch = int(issue.fetched_at.timestamp())
        first_epoch = int(issue.first_slot.timestamp())
        for step, forecast in enumerate(issue.intensities_g_per_kwh):
            slot_epoch = first_epoch + _SLOT_SECONDS * step
            actual = actual_by_epoch.get(slot_epoch)
            if actual is None or not start_epoch <= slot_epoch < end_epoch:
                continue
            position = _band_position(slot_epoch - issued_epoch)
            if position is None:
                continue
            tally = tallies.setdefault(_day_of(slot_epoch), _DayTally())
            tally.abs_error_sums[position] += abs(forecast - actual)
            tally.pairs[position] += 1
    return tallies


def _epoch_of(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


def _count_actuals_per_day(
    actual_by_epoch: Mapping[int, int], start: date, end: date
) -> dict[date, int]:
    start_epoch = _epoch_of(start)
    end_epoch = _epoch_of(end)
    counts: dict[date, int] = {}
    for slot_epoch in actual_by_epoch:
        if start_epoch <= slot_epoch < end_epoch:
            day = _day_of(slot_epoch)
            counts[day] = counts.get(day, 0) + 1
    return counts


def _unusable_reason(actual_count: int, tally: _DayTally) -> str | None:
    if actual_count < SLOTS_PER_DAY:
        return f"{actual_count} of {SLOTS_PER_DAY} half-hour actuals stored"
    for band, pairs in zip(BANDS, tally.pairs, strict=True):
        nominal = NOMINAL_PAIRS_PER_BAND_HOUR_PER_SLOT * band.hours * SLOTS_PER_DAY
        if pairs < MIN_BAND_SHARE * nominal:
            return f"{pairs} of {nominal} forecast pairs in the {band.label} band"
    return None


def _summarise(
    usable: Mapping[date, _DayTally], excluded: tuple[ExcludedDay, ...]
) -> NationalAccuracy:
    days = list(usable.values())
    pair_totals = [sum(day.pairs[position] for day in days) for position in range(len(BANDS))]
    error_totals = [
        sum(day.abs_error_sums[position] for day in days) for position in range(len(BANDS))
    ]
    point_maes = [
        errors / pairs if pairs else None
        for errors, pairs in zip(error_totals, pair_totals, strict=True)
    ]
    intervals = _intervals(days) if len(days) >= MIN_DAYS_FOR_INTERVAL else None
    bands = tuple(
        BandAccuracy(
            band,
            pair_totals[position],
            Estimate(point_maes[position], None if intervals is None else intervals[position]),
        )
        for position, band in enumerate(BANDS)
    )
    short_mae, long_mae = point_maes[0], point_maes[_LAST_BAND]
    difference = None if short_mae is None or long_mae is None else long_mae - short_mae
    return NationalAccuracy(
        bands,
        Estimate(difference, None if intervals is None else intervals[len(BANDS)]),
        tuple(usable),
        excluded,
    )


def _intervals(days: Sequence[_DayTally]) -> list[Interval]:
    """Percentile intervals per band, then for the difference, from resampling whole days.

    Every resample draws the same days for all bands, so the difference is paired.
    """
    rng = random.Random(SEED)  # noqa: S311 - a fixed seed makes the interval reproducible
    positions = range(len(BANDS))
    samples: list[list[float]] = [[] for _ in range(len(BANDS) + 1)]
    for _ in range(RESAMPLES):
        drawn = rng.choices(days, k=len(days))
        maes = [
            sum(day.abs_error_sums[position] for day in drawn)
            / sum(day.pairs[position] for day in drawn)
            for position in positions
        ]
        for position, mae in enumerate(maes):
            samples[position].append(mae)
        samples[len(BANDS)].append(maes[_LAST_BAND] - maes[0])
    return [_percentile_interval(values) for values in samples]


def _percentile_interval(values: Sequence[float]) -> Interval:
    cut_points = statistics.quantiles(values, n=INTERVAL_CUT_POINTS, method="inclusive")
    return Interval(cut_points[0], cut_points[-1])
