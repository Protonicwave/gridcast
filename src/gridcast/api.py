"""HTTP service that serves each region's outlook from the archive."""

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time
from typing import Annotated, Any

import psycopg
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from gridcast.accuracy import (
    MAX_LEAD_TIME,
    Estimate,
    NationalAccuracy,
    evaluate_national,
    evaluation_window,
)
from gridcast.archive import (
    CONNECT_TIMEOUT_SECONDS,
    DATABASE_URL_VARIABLE,
    latest_issue,
    latest_issues,
    national_actuals,
    national_issues,
)
from gridcast.forecast import SLOT_MINUTES, format_slot_time
from gridcast.outlook import DurationWindows, Outlook, build_outlook
from gridcast.regions import REGIONS
from gridcast.windows import Window

ALLOWED_ORIGIN_VARIABLE = "GRIDCAST_ALLOWED_ORIGIN"
CACHE_MAX_AGE_SECONDS = 60
ACCURACY_CACHE_MAX_AGE_SECONDS = 1_800
STATEMENT_TIMEOUT_MS = 5_000
# Far before the archive begins, and far enough from date.min that the window stays valid.
EARLIEST_UNTIL = date(2000, 1, 1)

_REGIONS_BY_ID = {region.api_id: region for region in REGIONS}
_FETCHED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

log = logging.getLogger(__name__)


def create_app(
    database_url: str,
    allowed_origin: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    """The service, reading the archive at `database_url` and allowing browsers on
    `allowed_origin` to call it. `now` is the clock the outlooks and the accuracy are cut at."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=[allowed_origin], allow_methods=["GET"])

    @app.get("/regions/{region_id}/outlook")
    def region_outlook(region_id: int, response: Response) -> dict[str, Any]:
        region = _REGIONS_BY_ID.get(region_id)
        if region is None:
            raise HTTPException(404, f"expected a region from 1 to 14, got {region_id}")
        with _archive_connection(database_url) as connection:
            issue = latest_issue(connection, region_id)
        if issue is None:
            raise HTTPException(503, "no forecast has been archived for this region")
        outlook = build_outlook(region, issue, now())
        if outlook is None:
            raise HTTPException(503, "the newest forecast has no half hour left")
        response.headers["Cache-Control"] = f"public, max-age={CACHE_MAX_AGE_SECONDS}"
        return _outlook_body(outlook)

    @app.get("/regions/outlook")
    def all_outlooks(response: Response) -> list[dict[str, Any]]:
        with _archive_connection(database_url) as connection:
            issues = latest_issues(connection)
        current = now()
        outlooks: list[Outlook] = []
        missing: list[int] = []
        for region in REGIONS:
            issue = issues.get(region.api_id)
            outlook = None if issue is None else build_outlook(region, issue, current)
            if outlook is None:
                missing.append(region.api_id)
            else:
                outlooks.append(outlook)
        if missing:
            raise HTTPException(503, f"no current forecast for regions {missing}")
        response.headers["Cache-Control"] = f"public, max-age={CACHE_MAX_AGE_SECONDS}"
        return [_outlook_body(outlook) for outlook in outlooks]

    @app.get("/accuracy/national")
    def national_accuracy(
        response: Response, until: Annotated[date | None, Query(ge=EARLIEST_UNTIL)] = None
    ) -> dict[str, Any]:
        today = now().astimezone(UTC).date()
        first_day, end_day = evaluation_window(today, until)
        first_slot, end_slot = _midnight(first_day), _midnight(end_day)
        with _archive_connection(database_url) as connection:
            issues = national_issues(connection, first_slot - MAX_LEAD_TIME, end_slot)
            actuals = national_actuals(connection, first_slot, end_slot)
        accuracy = evaluate_national(issues, actuals, today, until)
        response.headers["Cache-Control"] = f"public, max-age={ACCURACY_CACHE_MAX_AGE_SECONDS}"
        return _accuracy_body(accuracy, end_day)

    return app


def app_from_environment() -> FastAPI:
    """The service configured from the environment, for `uvicorn --factory`.

    Raises RuntimeError naming a variable that is not set.
    """
    settings: dict[str, str] = {}
    for variable in (DATABASE_URL_VARIABLE, ALLOWED_ORIGIN_VARIABLE):
        value = os.environ.get(variable)
        if not value:
            raise RuntimeError(f"expected {variable} to be set")
        settings[variable] = value
    return create_app(settings[DATABASE_URL_VARIABLE], settings[ALLOWED_ORIGIN_VARIABLE])


def _outlook_body(outlook: Outlook) -> dict[str, Any]:
    return {
        "regionId": outlook.region.api_id,
        "regionName": outlook.region.name,
        "fetchedAt": outlook.fetched_at.astimezone(UTC).strftime(_FETCHED_AT_FORMAT),
        "firstSlotStart": format_slot_time(outlook.first_slot_start.astimezone(UTC)),
        "slotMinutes": SLOT_MINUTES,
        "intensities": list(outlook.intensities_g_per_kwh),
        "windows": {str(hours): _windows_body(found) for hours, found in outlook.windows.items()},
    }


def _windows_body(found: DurationWindows) -> dict[str, Any]:
    return {
        "cleanest": _window_body(found.cleanest),
        "dirtiest": _window_body(found.dirtiest),
        "timingMatters": found.timing_matters,
    }


def _window_body(window: Window) -> dict[str, Any]:
    return {"start": window.start, "mean": window.mean}


@contextmanager
def _archive_connection(database_url: str) -> Iterator[psycopg.Connection[Any]]:
    """A connection to the archive; a database failure becomes a 503."""
    try:
        with psycopg.connect(
            database_url,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
        ) as connection:
            yield connection
    except psycopg.Error as err:
        # The class only: the message can hold the connection URL.
        log.error("archive unavailable error_class=%s", type(err).__name__)
        raise HTTPException(503, "the forecast archive is unavailable") from err


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _accuracy_body(accuracy: NationalAccuracy, until: date) -> dict[str, Any]:
    return {
        "until": until.isoformat(),
        "bands": [
            {
                "fromHours": band.band.start_hours,
                "toHours": band.band.end_hours,
                "pairs": band.pairs,
                **_estimate_body(band.estimate),
            }
            for band in accuracy.bands
        ],
        "difference": _estimate_body(accuracy.difference),
        "days": {
            "usable": [day.isoformat() for day in accuracy.usable_days],
            "excluded": [
                {"day": excluded.day.isoformat(), "reason": excluded.reason}
                for excluded in accuracy.excluded_days
            ],
        },
    }


def _estimate_body(estimate: Estimate) -> dict[str, Any]:
    interval = estimate.interval
    return {
        "maeGPerKwh": estimate.mae_g_per_kwh,
        "interval": None if interval is None else {"low": interval.low, "high": interval.high},
    }
