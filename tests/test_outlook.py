from datetime import UTC, datetime, timedelta

from gridcast.issues import StoredIssue
from gridcast.outlook import build_outlook
from gridcast.regions import REGIONS
from gridcast.windows import cleanest_window, dirtiest_window, timing_matters

LONDON = next(region for region in REGIONS if region.name == "London")
FIRST_SLOT = datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
FETCHED_AT = datetime(2026, 11, 19, 14, 5, 12, tzinfo=UTC)


def issue(*intensities: int) -> StoredIssue:
    return StoredIssue(FIRST_SLOT, intensities, FETCHED_AT)


def test_series_starts_at_the_slot_containing_now() -> None:
    now = FIRST_SLOT + timedelta(minutes=95)
    outlook = build_outlook(LONDON, issue(*range(10, 20)), now)
    assert outlook is not None
    assert outlook.intensities_g_per_kwh == (13, 14, 15, 16, 17, 18, 19)
    assert outlook.first_slot_start == FIRST_SLOT + timedelta(minutes=90)


def test_a_slot_that_ends_exactly_now_is_dropped() -> None:
    now = FIRST_SLOT + timedelta(minutes=60)
    outlook = build_outlook(LONDON, issue(*range(10, 20)), now)
    assert outlook is not None
    assert outlook.first_slot_start == now
    assert outlook.intensities_g_per_kwh[0] == 12


def test_keeps_the_whole_issue_when_now_is_before_its_first_slot() -> None:
    outlook = build_outlook(LONDON, issue(5, 6, 7), FIRST_SLOT - timedelta(minutes=10))
    assert outlook is not None
    assert outlook.intensities_g_per_kwh == (5, 6, 7)
    assert outlook.first_slot_start == FIRST_SLOT


def test_carries_the_region_and_fetch_time() -> None:
    outlook = build_outlook(LONDON, issue(5, 6), FIRST_SLOT)
    assert outlook is not None
    assert outlook.region == LONDON
    assert outlook.fetched_at == FETCHED_AT


def test_windows_match_the_window_rules_for_each_duration() -> None:
    intensities = [300, 250, 100, 120, 140, 160, 180, 200, 220, 400, 90, 80, 70, 60, 50, 40]
    outlook = build_outlook(LONDON, issue(*intensities), FIRST_SLOT)
    assert outlook is not None
    assert sorted(outlook.windows) == [1, 2, 3, 4]
    for hours, found in outlook.windows.items():
        cleanest = cleanest_window(intensities, hours * 2)
        dirtiest = dirtiest_window(intensities, hours * 2)
        assert found.cleanest == cleanest
        assert found.dirtiest == dirtiest
        assert found.timing_matters == timing_matters(cleanest, dirtiest)


def test_window_starts_index_the_remaining_series() -> None:
    now = FIRST_SLOT + timedelta(minutes=60)
    outlook = build_outlook(LONDON, issue(1, 1, 90, 90, 10, 10, 90, 90), now)
    assert outlook is not None
    assert outlook.windows[1].cleanest.start == 2


def test_a_duration_longer_than_what_remains_is_absent() -> None:
    outlook = build_outlook(LONDON, issue(*[100] * 5), FIRST_SLOT)
    assert outlook is not None
    assert sorted(outlook.windows) == [1, 2]


def test_a_single_slot_leaves_no_windows() -> None:
    outlook = build_outlook(LONDON, issue(100), FIRST_SLOT)
    assert outlook is not None
    assert outlook.windows == {}


def test_an_issue_with_no_slot_left_gives_none() -> None:
    now = FIRST_SLOT + timedelta(minutes=90)
    assert build_outlook(LONDON, issue(1, 2, 3), now) is None
