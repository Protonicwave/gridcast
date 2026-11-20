from datetime import datetime, timedelta

from factories import FIRST_SLOT
from test_archive import FETCHED_AT, OK, Archive, store, store_actuals

from gridcast.archive import national_actuals, national_issues, store_fetch
from gridcast.carbon_api import FetchResult
from gridcast.issues import Issue, Parsed, StoredIssue

HOUR = timedelta(hours=1)


def store_national_issue(archive: Archive, fetched_at: datetime, first_slot: datetime) -> None:
    result = FetchResult("https://example.invalid/", fetched_at, 200, b"{}", None, 1, 120)
    store_fetch(
        archive,
        endpoint="national_forecast",
        result=result,
        error=None,
        parsed=Parsed(issues=(Issue("national", 18, first_slot, (210, 220)),)),
    )


def test_reads_national_issues_fetched_in_the_range_oldest_first(archive: Archive) -> None:
    store_national_issue(archive, FETCHED_AT + 2 * HOUR, FIRST_SLOT + 2 * HOUR)
    store_national_issue(archive, FETCHED_AT, FIRST_SLOT)
    store_national_issue(archive, FETCHED_AT + 5 * HOUR, FIRST_SLOT + 5 * HOUR)
    found = national_issues(archive, FETCHED_AT, FETCHED_AT + 5 * HOUR)
    assert found == [
        StoredIssue(FIRST_SLOT, (210, 220), FETCHED_AT),
        StoredIssue(FIRST_SLOT + 2 * HOUR, (210, 220), FETCHED_AT + 2 * HOUR),
    ]


def test_leaves_the_regional_issues_out_of_the_national_ones(archive: Archive) -> None:
    store(archive, OK, None, slots=2)
    assert national_issues(archive, FETCHED_AT - HOUR, FETCHED_AT + HOUR) == []


def test_reads_national_actuals_in_the_range_and_omits_missing_ones(archive: Archive) -> None:
    store_actuals(archive, 150, None, 170, 180)
    found = national_actuals(archive, FIRST_SLOT, FIRST_SLOT + timedelta(minutes=45))
    assert found == {FIRST_SLOT: 150}


def test_reads_every_actual_published_in_a_wider_range(archive: Archive) -> None:
    store_actuals(archive, 150, None, 170)
    found = national_actuals(archive, FIRST_SLOT - HOUR, FIRST_SLOT + 5 * HOUR)
    assert found == {FIRST_SLOT: 150, FIRST_SLOT + timedelta(minutes=60): 170}
