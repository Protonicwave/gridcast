from datetime import timedelta

from factories import FIRST_SLOT, slot
from test_archive import FETCHED_AT, OK, Archive, store, store_actuals

from gridcast.archive import latest_issue, store_fetch
from gridcast.carbon_api import FetchResult
from gridcast.issues import Parsed, StoredIssue, parse_regional_issues


def test_latest_issue_is_none_for_an_empty_archive(archive: Archive) -> None:
    assert latest_issue(archive, 13) is None


def test_latest_issue_returns_the_newest_first_slot_with_its_fetch_time(archive: Archive) -> None:
    store(archive, OK, None, slots=2)
    later_fetched_at = FETCHED_AT + timedelta(minutes=30)
    later = FetchResult("https://example.invalid/", later_fetched_at, 200, b"{}", None, 1, 120)
    shifted = {"data": [slot(position) for position in range(1, 4)]}
    store_fetch(
        archive,
        endpoint="regional_forecast",
        result=later,
        error=None,
        parsed=Parsed(issues=parse_regional_issues(shifted)),
    )
    assert latest_issue(archive, 13) == StoredIssue(
        first_slot=FIRST_SLOT + timedelta(minutes=30),
        intensities_g_per_kwh=(14, 15, 16),
        fetched_at=later_fetched_at,
    )


def test_latest_issue_ignores_other_areas_and_the_national_feed(archive: Archive) -> None:
    store(archive, OK, None, slots=2)
    store_actuals(archive, 150)
    assert latest_issue(archive, 13) is not None
    assert latest_issue(archive, 19) is None
