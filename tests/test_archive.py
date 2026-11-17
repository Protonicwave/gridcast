from datetime import UTC, datetime

import psycopg
import pytest
from factories import payload

from gridcast.archive import store_fetch
from gridcast.carbon_api import FetchResult
from gridcast.issues import parse_regional_issues

Archive = psycopg.Connection[tuple[object, ...]]

FETCHED_AT = datetime(2026, 11, 17, 11, 50, tzinfo=UTC)
OK = FetchResult("https://example.invalid/", FETCHED_AT, 200, b"{}", None, 1, 120)


def store(archive: Archive, result: FetchResult, error: str | None, *, slots: int) -> int:
    issues = parse_regional_issues(payload(slots)) if slots else ()
    return store_fetch(
        archive,
        endpoint="regional_forecast",
        result=result,
        error=error,
        issues=issues,
    )


def test_counts_the_issues_it_adds(archive: Archive) -> None:
    assert store(archive, OK, None, slots=2) == 18


def test_keeps_the_first_issue_for_an_area_and_first_slot(archive: Archive) -> None:
    store(archive, OK, None, slots=2)
    assert store(archive, OK, None, slots=3) == 0
    lengths = archive.execute(
        "select distinct cardinality(intensities_g_per_kwh) from forecast_issue"
    ).fetchall()
    assert lengths == [(2,)]


def test_records_a_fetch_with_no_issues(archive: Archive) -> None:
    assert store(archive, OK, "data holds no slots", slots=0) == 0
    [(count,)] = archive.execute("select count(*) from api_fetch").fetchall()
    assert count == 1


def test_refuses_a_fetch_with_neither_body_nor_error(archive: Archive) -> None:
    empty = FetchResult("https://example.invalid/", FETCHED_AT, None, None, None, 1, 120)
    with pytest.raises(psycopg.errors.CheckViolation):
        store(archive, empty, None, slots=0)
