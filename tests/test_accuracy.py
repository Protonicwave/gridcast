from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import pytest

from gridcast.accuracy import (
    BANDS,
    MAX_DAYS_EVALUATED,
    Band,
    ExcludedDay,
    NationalAccuracy,
    evaluate_national,
    horizon_band,
)
from gridcast.issues import StoredIssue

ACTUAL = 200
FETCH_DELAY = timedelta(minutes=5)
HALF_HOUR = timedelta(minutes=30)
# Issues for one day reach its slots only; days this far apart do not share issues.
DAY_SPACING = 6
FIRST_DAY = date(2026, 6, 1)
ISSUED_AT = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

# Pairs per slot in each band for 96-slot issues fetched five minutes after their first
# slot: the last band loses the exact 48 h lead time.
PAIRS_PER_DAY = (480, 576, 1152, 2256)


def midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def actuals_for(day: date) -> dict[datetime, int]:
    return {midnight(day) + HALF_HOUR * step: ACTUAL for step in range(48)}


def issues_for(day: date, errors: Sequence[int], slots_per_issue: int = 96) -> list[StoredIssue]:
    """Issues fetched every half hour from 48 h before `day` to its end, each forecasting
    ACTUAL plus the given error for the band its lead time falls in."""
    issues = []
    for fetch in range(-96, 48):
        first_slot = midnight(day) + HALF_HOUR * fetch
        fetched_at = first_slot + FETCH_DELAY
        intensities = []
        for step in range(slots_per_issue):
            band = horizon_band(fetched_at, first_slot + HALF_HOUR * step)
            error = 0 if band is None else errors[BANDS.index(band)]
            intensities.append(ACTUAL + error)
        issues.append(StoredIssue(first_slot, tuple(intensities), fetched_at))
    return issues


def evaluate_days(
    day_errors: Sequence[Sequence[int]], until: date | None = None, today: date | None = None
) -> NationalAccuracy:
    """Evaluate one day per entry, each with its own error per band."""
    issues: list[StoredIssue] = []
    actuals: dict[datetime, int] = {}
    for number, errors in enumerate(day_errors):
        day = FIRST_DAY + timedelta(days=DAY_SPACING * number)
        issues += issues_for(day, errors)
        actuals |= actuals_for(day)
    last_day = FIRST_DAY + timedelta(days=DAY_SPACING * len(day_errors))
    return evaluate_national(issues, actuals, today or last_day, until)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (-30, None),
        (0, None),
        (59, None),
        (60, BANDS[0]),
        (359, BANDS[0]),
        (360, BANDS[1]),
        (719, BANDS[1]),
        (720, BANDS[2]),
        (1439, BANDS[2]),
        (1440, BANDS[3]),
        (2880, BANDS[3]),
        (2881, None),
    ],
)
def test_places_a_lead_time_in_the_band_starting_at_or_below_it(
    minutes: int, expected: Band | None
) -> None:
    assert horizon_band(ISSUED_AT, ISSUED_AT + timedelta(minutes=minutes)) == expected


def test_measures_the_mean_absolute_error_of_each_band_over_its_pairs() -> None:
    accuracy = evaluate_days([(2, 4, 6, -8), (4, 4, 8, 12)])
    assert [band.band for band in accuracy.bands] == list(BANDS)
    assert [band.pairs for band in accuracy.bands] == [2 * pairs for pairs in PAIRS_PER_DAY]
    assert [band.estimate.mae_g_per_kwh for band in accuracy.bands] == [3, 4, 7, 10]


def test_reports_the_long_band_minus_the_short_band_as_the_difference() -> None:
    accuracy = evaluate_days([(2, 4, 6, 8), (4, 4, 8, 12)])
    assert accuracy.difference.mae_g_per_kwh == 7


def test_lists_the_utc_days_used() -> None:
    accuracy = evaluate_days([(1, 1, 1, 1), (1, 1, 1, 1)])
    assert accuracy.usable_days == (FIRST_DAY, FIRST_DAY + timedelta(days=DAY_SPACING))
    assert accuracy.excluded_days == ()


def test_excludes_a_day_with_a_missing_actual_and_says_how_many() -> None:
    issues = issues_for(FIRST_DAY, (1, 1, 1, 1))
    actuals = actuals_for(FIRST_DAY)
    del actuals[midnight(FIRST_DAY) + HALF_HOUR * 10]
    accuracy = evaluate_national(issues, actuals, FIRST_DAY + timedelta(days=2))
    assert accuracy.usable_days == ()
    assert accuracy.excluded_days == (ExcludedDay(FIRST_DAY, "47 of 48 half-hour actuals stored"),)


def test_excludes_a_day_with_actuals_and_no_issues() -> None:
    accuracy = evaluate_national([], actuals_for(FIRST_DAY), FIRST_DAY + timedelta(days=2))
    assert accuracy.excluded_days == (
        ExcludedDay(FIRST_DAY, "0 of 480 forecast pairs in the 1 to 6 h band"),
    )


def test_excludes_a_day_whose_longest_band_is_too_thin() -> None:
    issues = issues_for(FIRST_DAY, (1, 1, 1, 1), slots_per_issue=48)
    accuracy = evaluate_national(issues, actuals_for(FIRST_DAY), FIRST_DAY + timedelta(days=2))
    assert accuracy.excluded_days == (
        ExcludedDay(FIRST_DAY, "0 of 2304 forecast pairs in the 24 to 48 h band"),
    )


def test_a_band_with_no_usable_day_has_no_error() -> None:
    accuracy = evaluate_national([], {}, FIRST_DAY)
    assert accuracy.usable_days == ()
    assert [band.pairs for band in accuracy.bands] == [0, 0, 0, 0]
    assert all(band.estimate.mae_g_per_kwh is None for band in accuracy.bands)
    assert accuracy.difference.mae_g_per_kwh is None


def test_leaves_the_intervals_empty_below_seven_usable_days() -> None:
    accuracy = evaluate_days([(1, 2, 3, 4)] * 6)
    assert len(accuracy.usable_days) == 6
    assert all(band.estimate.interval is None for band in accuracy.bands)
    assert accuracy.difference.interval is None
    assert accuracy.difference.mae_g_per_kwh == 3


def test_gives_each_band_an_interval_around_its_error_from_seven_days() -> None:
    errors = [(day + 1, day + 2, day + 3, day + 4) for day in range(7)]
    accuracy = evaluate_days(errors)
    for position, band in enumerate(accuracy.bands):
        interval = band.estimate.interval
        assert interval is not None
        assert band.estimate.mae_g_per_kwh == 4 + position
        assert 1 + position < interval.low < 4 + position < interval.high < 7 + position


def test_repeats_the_same_interval_for_the_same_days() -> None:
    errors = [(day + 1, 0, 0, 2 * day + 5) for day in range(7)]
    assert evaluate_days(errors) == evaluate_days(errors)


def test_collapses_the_interval_to_the_error_when_every_day_is_alike() -> None:
    accuracy = evaluate_days([(2, 3, 4, 10)] * 7)
    for band, expected in zip(accuracy.bands, (2, 3, 4, 10), strict=True):
        assert band.estimate.interval is not None
        assert band.estimate.interval.low == pytest.approx(expected)
        assert band.estimate.interval.high == pytest.approx(expected)
    assert accuracy.difference.interval is not None
    assert accuracy.difference.interval.low == pytest.approx(8)
    assert accuracy.difference.interval.high == pytest.approx(8)


def test_resamples_the_same_days_for_every_band_so_the_difference_is_paired() -> None:
    # The short band's error swings from day to day but the long band's moves with it,
    # so the difference is always 8 and its interval must not widen with the swing.
    accuracy = evaluate_days([(day, 0, 0, day + 8) for day in range(1, 8)])
    short = accuracy.bands[0].estimate.interval
    assert short is not None
    assert short.high - short.low > 1
    assert accuracy.difference.interval is not None
    assert accuracy.difference.interval.low == pytest.approx(8)
    assert accuracy.difference.interval.high == pytest.approx(8)


def test_leaves_out_the_day_the_cut_names_and_later_ones() -> None:
    first = FIRST_DAY
    second = FIRST_DAY + timedelta(days=DAY_SPACING)
    issues = issues_for(first, (1, 1, 1, 1)) + issues_for(second, (1, 1, 1, 1))
    actuals = actuals_for(first) | actuals_for(second)
    today = second + timedelta(days=3)
    assert evaluate_national(issues, actuals, today).usable_days == (first, second)
    assert evaluate_national(issues, actuals, today, until=second).usable_days == (first,)
    assert evaluate_national(issues, actuals, second).usable_days == (first,)
    assert evaluate_national(issues, actuals, first, until=today).usable_days == ()


def test_reads_only_the_days_in_the_window_before_the_cut() -> None:
    end = FIRST_DAY + timedelta(days=MAX_DAYS_EVALUATED + 10)
    inside = end - timedelta(days=MAX_DAYS_EVALUATED)
    outside = inside - timedelta(days=DAY_SPACING)
    issues = issues_for(inside, (1, 1, 1, 1)) + issues_for(outside, (1, 1, 1, 1))
    actuals = actuals_for(inside) | actuals_for(outside)
    assert evaluate_national(issues, actuals, end).usable_days == (inside,)
