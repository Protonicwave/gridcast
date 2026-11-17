from datetime import UTC, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest
from factories import FIRST_SLOT, national_payload, payload

from gridcast.archive import store_fetch
from gridcast.carbon_api import FetchResult
from gridcast.issues import Parsed, parse_national_actuals, parse_regional_issues

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
        parsed=Parsed(issues=issues),
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


def store_actuals(archive: Archive, *actuals: int | None) -> int:
    return store_fetch(
        archive,
        endpoint="national_actual",
        result=OK,
        error=None,
        parsed=Parsed(actuals=parse_national_actuals(national_payload(*actuals))),
    )


def actuals_stored(archive: Archive) -> list[object]:
    rows = archive.execute(
        "select intensity_g_per_kwh from national_actual order by slot_start"
    ).fetchall()
    return [row[0] for row in rows]


def test_stores_actuals_and_counts_them(archive: Archive) -> None:
    assert store_actuals(archive, 150, 160, None) == 3
    assert actuals_stored(archive) == [150, 160, None]


def test_fills_in_an_actual_a_later_fetch_brings(archive: Archive) -> None:
    store_actuals(archive, 150, None)
    assert store_actuals(archive, 150, 170, None) == 2
    assert actuals_stored(archive) == [150, 170, None]


def test_a_missing_actual_never_replaces_a_stored_one_but_a_revision_does(
    archive: Archive,
) -> None:
    store_actuals(archive, 150, 160)
    assert store_actuals(archive, None, 999) == 1
    assert actuals_stored(archive) == [150, 999]


def test_an_actual_rewritten_to_the_same_value_changes_nothing(archive: Archive) -> None:
    store_actuals(archive, 150)
    assert store_actuals(archive, 150) == 0


def test_lists_each_forecast_value_with_its_horizon(archive: Archive) -> None:
    store(archive, OK, None, slots=3)
    rows = archive.execute(
        "select slot_start, horizon_minutes, intensity_g_per_kwh from forecast_value"
        " where feed = 'regional' and area_id = 2 order by slot_start"
    ).fetchall()
    assert rows == [
        (FIRST_SLOT + timedelta(minutes=30 * position), 30 * position - 20, 2 + position)
        for position in range(3)
    ]


def test_reports_the_share_of_half_hours_recorded_each_day(archive: Archive) -> None:
    def fetched(hour: int, minute: int, error: str | None) -> FetchResult:
        return FetchResult(
            "https://example.invalid/",
            datetime(2026, 11, 16, hour, minute, tzinfo=UTC),
            200 if error is None else None,
            b"{}" if error is None else None,
            error,
            1,
            120,
        )

    # Two good fetches in the 00:00 half hour, one in 00:30, and a failed one at 01:05.
    for hour, minute, error in ((0, 5, None), (0, 10, None), (0, 35, None), (1, 5, "timed out")):
        store(archive, fetched(hour, minute, error), error, slots=0)
    [(day_utc, recorded, share)] = archive.execute(
        "select day_utc, half_hours_recorded, share_recorded from collection_coverage"
    ).fetchall()
    assert (str(day_utc), recorded) == ("2026-11-16", 2)
    assert isinstance(share, Decimal)
    assert float(share) == pytest.approx(2 / 48)


def test_collector_role_may_insert_but_not_delete_or_alter(archive: Archive) -> None:
    store(archive, OK, None, slots=1)
    archive.commit()
    archive.execute("set role gridcast_collector")
    store(archive, OK, None, slots=2)
    for statement in (
        "delete from forecast_issue",
        "update forecast_issue set area_id = 1",
        "update api_fetch set error = 'x'",
        "alter table forecast_issue add column extra int",
        "drop table api_fetch",
        "truncate national_actual",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            archive.execute(statement)
        archive.rollback()
        archive.execute("set role gridcast_collector")
