"""Writes to the PostgreSQL archive of API fetches and forecast issues."""

import gzip
from collections.abc import Sequence
from typing import Any, Literal

import psycopg

from gridcast.carbon_api import FetchResult
from gridcast.issues import Issue

DATABASE_URL_VARIABLE = "GRIDCAST_DATABASE_URL"
CONNECT_TIMEOUT_SECONDS = 10

Endpoint = Literal["regional_forecast"]


def store_fetch(
    connection: psycopg.Connection[Any],
    *,
    endpoint: Endpoint,
    result: FetchResult,
    error: str | None,
    issues: Sequence[Issue],
) -> int:
    """Record a fetch, its body gzipped, and its issues in one transaction.

    `error` is the fetch's failure or the parser's. An issue already archived for the
    same feed, area and first slot is left as it was. Returns the number of issues
    added.
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
