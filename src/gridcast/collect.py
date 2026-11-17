"""The collector: fetches NESO's forecasts and actuals and stores them in the archive."""

import argparse
import http.client
import json
import logging
import os
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from gridcast.archive import (
    CONNECT_TIMEOUT_SECONDS,
    DATABASE_URL_VARIABLE,
    Endpoint,
    store_fetch,
)
from gridcast.carbon_api import (
    FetchResult,
    fetch,
    national_actuals_path,
    national_forecast_path,
    regional_forecast_path,
)
from gridcast.issues import (
    Parsed,
    parse_national_actuals,
    parse_national_issue,
    parse_regional_issues,
)

EXIT_FAILED = 1
EXIT_USAGE = 2

# healthchecks.io emails when these pings stop, so a lost ping is covered by its grace period.
HEALTHCHECK_URL_VARIABLE = "GRIDCAST_HEALTHCHECK_URL"
HEALTHCHECK_TIMEOUT_SECONDS = 10

# Actuals arrive late and are sometimes revised, so each run asks again for the last day.
ACTUALS_LOOKBACK = timedelta(hours=24)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Call:
    endpoint: Endpoint
    path: Callable[[datetime], str]
    parse: Callable[[object], Parsed]


_CALLS = (
    _Call(
        "regional_forecast",
        regional_forecast_path,
        lambda payload: Parsed(issues=parse_regional_issues(payload)),
    ),
    _Call(
        "national_forecast",
        national_forecast_path,
        lambda payload: Parsed(issues=(parse_national_issue(payload),)),
    ),
    _Call(
        "national_actual",
        lambda now: national_actuals_path(now - ACTUALS_LOOKBACK, now),
        lambda payload: Parsed(actuals=parse_national_actuals(payload)),
    ),
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run once. Exits 1 if any fetch, parse or write failed, 2 if misconfigured.

    Pings the URL in $GRIDCAST_HEALTHCHECK_URL, if set, once the regional forecast is stored.
    """
    argparse.ArgumentParser(
        description="Fetch NESO's regional and national forecasts and the national actuals "
        f"and store them, with the raw responses, in the database at ${DATABASE_URL_VARIABLE}. "
        f"Ping ${HEALTHCHECK_URL_VARIABLE}, if set, once the regional forecast is stored."
    ).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database_url = os.environ.get(DATABASE_URL_VARIABLE)
    if not database_url:
        print(f"gridcast-collect: {DATABASE_URL_VARIABLE} is not set", file=sys.stderr)
        return EXIT_USAGE
    healthcheck_url = os.environ.get(HEALTHCHECK_URL_VARIABLE) or None
    if healthcheck_url is not None and not healthcheck_url.startswith("https://"):
        # The URL itself is a credential, so the message names only the variable.
        print(
            f"gridcast-collect: {HEALTHCHECK_URL_VARIABLE} must start with https://",
            file=sys.stderr,
        )
        return EXIT_USAGE
    started = time.monotonic()
    now = datetime.now(UTC)
    try:
        with psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as connection:
            # Each call is stored on its own, so one failing leaves the others archived.
            outcomes = {call.endpoint: _run(connection, call, now) for call in _CALLS}
    except psycopg.Error as err:
        log.error("archive connection failed error=%r", str(err))
        return EXIT_FAILED
    if healthcheck_url is not None and outcomes["regional_forecast"]:
        _ping(healthcheck_url)
    log.info("run finished seconds=%.1f", time.monotonic() - started)
    return 0 if all(outcomes.values()) else EXIT_FAILED


def _ping(url: str) -> None:
    """Tell the health check the regional forecast reached the archive. Failure is only logged."""
    # S310 warns that urlopen accepts file: URLs; main accepts only https URLs here.
    request = urllib.request.Request(url, headers={"User-Agent": "gridcast-collector"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=HEALTHCHECK_TIMEOUT_SECONDS) as response:  # noqa: S310
            status: int = response.status
    except (OSError, http.client.HTTPException) as err:
        log.error("health check ping failed error=%r", f"{type(err).__name__}: {err}")
        return
    log.info("health check pinged status=%d", status)


def _run(connection: psycopg.Connection[Any], call: _Call, now: datetime) -> bool:
    """Fetch, parse and store one call. True if it was stored without error."""
    result = fetch(call.path(now))
    parsed, error = _parse(result, call.parse)
    try:
        stored = store_fetch(
            connection,
            endpoint=call.endpoint,
            result=result,
            error=error,
            parsed=parsed,
        )
    except psycopg.Error as err:
        log.error("archive write failed endpoint=%s error=%r", call.endpoint, str(err))
        return False
    log.info(
        "fetch stored endpoint=%s status=%s attempts=%d duration_ms=%d rows_stored=%d error=%r",
        call.endpoint,
        result.status,
        result.attempts,
        result.duration_ms,
        stored,
        error,
    )
    return error is None


def _parse(result: FetchResult, parse: Callable[[object], Parsed]) -> tuple[Parsed, str | None]:
    """What a fetched body holds, or nothing and the reason there is nothing."""
    if result.body is None:
        return Parsed(), result.error
    try:
        payload = json.loads(result.body)
    except ValueError as err:
        return Parsed(), f"body is not JSON: {err}"
    try:
        return parse(payload), None
    except ValueError as err:
        return Parsed(), str(err)
