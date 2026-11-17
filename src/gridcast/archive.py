"""Writes to the PostgreSQL archive of API fetches and forecast issues."""

import gzip
from collections.abc import Sequence
from typing import Any, Literal

import psycopg

from gridcast.carbon_api import FetchResult
from gridcast.issues import Actual, Issue, Parsed

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
