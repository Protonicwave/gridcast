"""Bounded GET requests to NESO's Carbon Intensity API."""

import http.client
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

from gridcast.forecast import format_slot_time

BASE_URL = "https://api.carbonintensity.org.uk"
REQUEST_TIMEOUT_SECONDS = 10
RETRY_WAITS_SECONDS = (5, 15)
MAX_ATTEMPTS = len(RETRY_WAITS_SECONDS) + 1
MAX_BODY_BYTES = 5 * 1024 * 1024

_HTTP_OK = 200
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500
_HEADERS = {"Accept": "application/json", "User-Agent": "gridcast-collector"}


@dataclass(frozen=True, slots=True)
class _Attempt:
    status: int | None
    body: bytes | None
    error: str | None
    is_retryable: bool


@dataclass(frozen=True, slots=True)
class FetchResult:
    """The outcome of one bounded GET, after any retries.

    `fetched_at` is when the first attempt started. `body` is the response body when
    `error` is None. `status` is the last HTTP status received, or None if no attempt
    got a response.
    """

    url: str
    fetched_at: datetime
    status: int | None
    body: bytes | None
    error: str | None
    attempts: int
    duration_ms: int


def regional_forecast_path(moment: datetime) -> str:
    """The regional 48-hour forecast starting from the half hour that holds `moment`."""
    return f"/regional/intensity/{format_slot_time(moment)}/fw48h"


def fetch(path: str) -> FetchResult:
    """GET `path` under BASE_URL, retrying timeouts, connection errors, HTTP 429 and 5xx.

    Never raises for a network or HTTP failure: the failure is returned in `error`.
    """
    url = BASE_URL + path
    fetched_at = datetime.now(UTC)
    started = time.monotonic()
    attempts = 1
    outcome = _attempt(url)
    while outcome.is_retryable and attempts < MAX_ATTEMPTS:
        time.sleep(RETRY_WAITS_SECONDS[attempts - 1])
        attempts += 1
        outcome = _attempt(url)
    duration_ms = round((time.monotonic() - started) * 1000)
    return FetchResult(
        url, fetched_at, outcome.status, outcome.body, outcome.error, attempts, duration_ms
    )


def _attempt(url: str) -> _Attempt:
    # S310 warns that urlopen accepts file: URLs; every URL here starts with BASE_URL.
    request = urllib.request.Request(url, headers=_HEADERS)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
            status: int = response.status
            body: bytes = response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as err:
        is_retryable = err.code == _HTTP_TOO_MANY_REQUESTS or err.code >= _HTTP_SERVER_ERROR
        return _Attempt(err.code, None, f"HTTP {err.code} {err.reason}", is_retryable)
    except (OSError, http.client.HTTPException) as err:
        # URLError, timeouts and dropped connections are all OSError subclasses.
        return _Attempt(None, None, f"{type(err).__name__}: {err}", is_retryable=True)
    if status != _HTTP_OK:
        return _Attempt(status, None, f"HTTP {status}, expected {_HTTP_OK}", is_retryable=False)
    if len(body) > MAX_BODY_BYTES:
        return _Attempt(status, None, f"body exceeds {MAX_BODY_BYTES} bytes", is_retryable=False)
    return _Attempt(status, body, None, is_retryable=False)
