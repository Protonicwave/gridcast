"""Writes to the PostgreSQL archive of API fetches and forecast issues."""

import gzip
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

import psycopg

from gridcast.carbon_api import FetchResult
from gridcast.issues import Actual, Issue, Parsed, StoredIssue

DATABASE_URL_VARIABLE = "GRIDCAST_DATABASE_URL"
CONNECT_TIMEOUT_SECONDS = 10

Endpoint = Literal["regional_forecast", "national_forecast", "national_actual"]


def store_fetch(
    connection: psycopg.Connection[Any],
    *,
    endpoint: Endpoint,
    result: FetchResult,
    error: str | None,
    parsed: Parsed,
) -> int:
    """Record a fetch, its body gzipped, and what was parsed from it in one transaction.

    `error` is the fetch's failure or the parser's. An issue already archived for the
    same feed, area and first slot is left as it was. A stored actual changes only to
    a different measurement: a missing one never replaces it. Returns the number of
    issues added plus the number of actuals added or changed.
    """
    raw_gzip = None if result.body is None else gzip.compress(result.body, mtime=0)
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            "insert into api_fetch (endpoint, url, fetched_at, attempts, duration_ms,"
            " http_status, raw_gzip, error) values (%s, %s, %s, %s, %s, %s, %s, %s)"
            " returning fetch_id",
            (
                endpoint,
                result.url,
                result.fetched_at,
                result.attempts,
                result.duration_ms,
                result.status,
                raw_gzip,
                error,
            ),
        )
        [(fetch_id,)] = cursor.fetchall()
        issues_added = _add_issues(cursor, fetch_id, parsed.issues)
        return issues_added + _add_actuals(cursor, fetch_id, parsed.actuals)


def latest_issue(connection: psycopg.Connection[Any], area_id: int) -> StoredIssue | None:
    """The regional issue of `area_id` with the latest first slot, or None if there is none."""
    row = connection.execute(
        "select issue.first_slot, issue.intensities_g_per_kwh, api_fetch.fetched_at"
        " from forecast_issue as issue inner join api_fetch on issue.fetch_id = api_fetch.fetch_id"
        " where issue.feed = 'regional' and issue.area_id = %s"
        " order by issue.first_slot desc limit 1",
        (area_id,),
    ).fetchone()
    if row is None:
        return None
    first_slot, intensities, fetched_at = row
    return StoredIssue(first_slot, tuple(intensities), fetched_at)


def national_issues(
    connection: psycopg.Connection[Any], since: datetime, until: datetime
) -> list[StoredIssue]:
    """The national issues fetched from `since` up to but not including `until`, oldest first."""
    rows = connection.execute(
        "select issue.first_slot, issue.intensities_g_per_kwh, api_fetch.fetched_at"
        " from forecast_issue as issue inner join api_fetch on issue.fetch_id = api_fetch.fetch_id"
        " where issue.feed = 'national'"
        " and api_fetch.fetched_at >= %s and api_fetch.fetched_at < %s"
        " order by api_fetch.fetched_at",
        (since, until),
    ).fetchall()
    return [
        StoredIssue(first_slot, tuple(intensities), fetched_at)
        for first_slot, intensities, fetched_at in rows
    ]


def national_actuals(
    connection: psycopg.Connection[Any], since: datetime, until: datetime
) -> dict[datetime, int]:
    """The measured national intensity of each half hour starting from `since` up to but not
    including `until`. Half hours NESO has not yet measured are left out."""
    rows = connection.execute(
        "select slot_start, intensity_g_per_kwh from national_actual"
        " where slot_start >= %s and slot_start < %s and intensity_g_per_kwh is not null",
        (since, until),
    ).fetchall()
    return dict(rows)


def _add_issues(cursor: psycopg.Cursor[Any], fetch_id: int, issues: Sequence[Issue]) -> int:
    cursor.executemany(
        "insert into forecast_issue (feed, area_id, first_slot, fetch_id,"
        " intensities_g_per_kwh) values (%s, %s, %s, %s, %s)"
        " on conflict (feed, area_id, first_slot) do nothing",
        [
            (
                issue.feed,
                issue.area_id,
                issue.first_slot,
                fetch_id,
                list(issue.intensities_g_per_kwh),
            )
            for issue in issues
        ],
    )
    return cursor.rowcount


def _add_actuals(cursor: psycopg.Cursor[Any], fetch_id: int, actuals: Sequence[Actual]) -> int:
    cursor.executemany(
        "insert into national_actual (slot_start, intensity_g_per_kwh, fetch_id)"
        " values (%s, %s, %s)"
        " on conflict (slot_start) do update"
        " set intensity_g_per_kwh = excluded.intensity_g_per_kwh, fetch_id = excluded.fetch_id"
        " where excluded.intensity_g_per_kwh is not null"
        " and national_actual.intensity_g_per_kwh is distinct from excluded.intensity_g_per_kwh",
        [(actual.slot_start, actual.intensity_g_per_kwh, fetch_id) for actual in actuals],
    )
    return cursor.rowcount
