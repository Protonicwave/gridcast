from datetime import timedelta

from factories import FIRST_SLOT, slot
from test_archive import FETCHED_AT, OK, Archive, store, store_actuals

from gridcast.archive import latest_issues, store_fetch
from gridcast.carbon_api import FetchResult
from gridcast.issues import Parsed, StoredIssue, parse_regional_issues


def test_latest_issues_is_empty_for_an_empty_archive(archive: Archive) -> None:
    assert latest_issues(archive) == {}


def test_latest_issues_returns_one_newest_issue_per_regional_area(archive: Archive) -> None:
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
    store_actuals(archive, 150)
    issues = latest_issues(archive)
    assert sorted(issues) == list(range(1, 19))
    assert issues[13] == StoredIssue(
        first_slot=FIRST_SLOT + timedelta(minutes=30),
        intensities_g_per_kwh=(14, 15, 16),
        fetched_at=later_fetched_at,
    )
