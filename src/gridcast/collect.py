"""The collector: fetches NESO's regional forecast and stores it in the archive."""

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime

import psycopg

from gridcast.archive import CONNECT_TIMEOUT_SECONDS, DATABASE_URL_VARIABLE, store_fetch
from gridcast.carbon_api import FetchResult, fetch, regional_forecast_path
from gridcast.issues import Issue, parse_regional_issues

EXIT_FAILED = 1
EXIT_USAGE = 2

log = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Run once. Exits 1 if the fetch, the parse or the write failed, 2 if misconfigured."""
    argparse.ArgumentParser(
        description="Fetch NESO's regional 48-hour forecast and store it, with the raw "
        f"response, in the database at ${DATABASE_URL_VARIABLE}."
    ).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database_url = os.environ.get(DATABASE_URL_VARIABLE)
    if not database_url:
        print(f"gridcast-collect: {DATABASE_URL_VARIABLE} is not set", file=sys.stderr)
        return EXIT_USAGE
    started = time.monotonic()
    result = fetch(regional_forecast_path(datetime.now(UTC)))
    issues, error = _parse(result)
    try:
        with psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as connection:
            added = store_fetch(
                connection,
                endpoint="regional_forecast",
                result=result,
                error=error,
                issues=issues,
            )
    except psycopg.Error as err:
        log.error("archive write failed endpoint=regional_forecast error=%r", str(err))
        return EXIT_FAILED
    log.info(
        "fetch stored endpoint=regional_forecast status=%s attempts=%d duration_ms=%d "
        "issues_added=%d error=%r",
        result.status,
        result.attempts,
        result.duration_ms,
        added,
        error,
    )
    log.info("run finished seconds=%.1f", time.monotonic() - started)
    return EXIT_FAILED if error is not None else 0


def _parse(result: FetchResult) -> tuple[tuple[Issue, ...], str | None]:
    """The issues in a fetched body, or no issues and the reason there are none."""
    if result.body is None:
        return (), result.error
    try:
        payload = json.loads(result.body)
    except ValueError as err:
        return (), f"body is not JSON: {err}"
    try:
        return parse_regional_issues(payload), None
    except ValueError as err:
        return (), str(err)
