import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest
from fakes import FakeResponse, FakeServer, http_error

from gridcast.carbon_api import (
    BASE_URL,
    MAX_BODY_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    fetch,
    regional_forecast_path,
)

PATH = "/regional/intensity/2026-11-17T11:50Z/fw48h"


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", recorded.append)
    return recorded


def serve(monkeypatch: pytest.MonkeyPatch, *outcomes: FakeResponse | Exception) -> FakeServer:
    server = FakeServer(*outcomes)
    monkeypatch.setattr(urllib.request, "urlopen", server.urlopen)
    return server


def test_returns_body_of_first_successful_answer(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    server = serve(monkeypatch, FakeResponse(b'{"data": []}'))
    result = fetch(PATH)
    assert (result.status, result.body, result.error, result.attempts) == (
        200,
        b'{"data": []}',
        None,
        1,
    )
    assert result.url == BASE_URL + PATH
    assert result.duration_ms >= 0
    assert server.requests == [(BASE_URL + PATH, REQUEST_TIMEOUT_SECONDS)]
    assert waits == []


@pytest.mark.parametrize(
    "failure",
    [http_error(503), http_error(429), TimeoutError("timed out"), urllib.error.URLError("down")],
)
def test_retries_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch, waits: list[float], failure: Exception
) -> None:
    serve(monkeypatch, failure, FakeResponse(b"{}"))
    result = fetch(PATH)
    assert (result.body, result.error, result.attempts) == (b"{}", None, 2)
    assert waits == [5]


def test_stops_after_three_attempts(monkeypatch: pytest.MonkeyPatch, waits: list[float]) -> None:
    server = serve(monkeypatch, http_error(502), http_error(503), http_error(504))
    result = fetch(PATH)
    assert (result.status, result.body, result.attempts) == (504, None, 3)
    assert result.error == "HTTP 504 Reason"
    assert waits == [5, 15]
    assert len(server.requests) == 3


def test_reports_a_timeout_with_no_status(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    serve(monkeypatch, *(TimeoutError("timed out") for _ in range(3)))
    result = fetch(PATH)
    assert (result.status, result.error, result.attempts) == (None, "TimeoutError: timed out", 3)


def test_does_not_retry_not_found(monkeypatch: pytest.MonkeyPatch, waits: list[float]) -> None:
    serve(monkeypatch, http_error(404))
    result = fetch(PATH)
    assert (result.status, result.body, result.error, result.attempts) == (
        404,
        None,
        "HTTP 404 Reason",
        1,
    )
    assert waits == []


def test_rejects_a_success_status_other_than_ok(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    serve(monkeypatch, FakeResponse(b"", status=204))
    result = fetch(PATH)
    assert (result.status, result.body, result.error) == (204, None, "HTTP 204, expected 200")


def test_stops_reading_a_body_over_the_limit(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    serve(monkeypatch, FakeResponse(b"x" * (MAX_BODY_BYTES + 2)))
    result = fetch(PATH)
    assert (result.body, result.error, result.attempts) == (
        None,
        f"body exceeds {MAX_BODY_BYTES} bytes",
        1,
    )


def test_accepts_a_body_at_the_limit(monkeypatch: pytest.MonkeyPatch, waits: list[float]) -> None:
    serve(monkeypatch, FakeResponse(b"x" * MAX_BODY_BYTES))
    result = fetch(PATH)
    assert result.error is None
    assert result.body is not None
    assert len(result.body) == MAX_BODY_BYTES


def test_regional_forecast_path_names_the_minute() -> None:
    moment = datetime(2026, 11, 17, 11, 50, 42, tzinfo=UTC)
    assert regional_forecast_path(moment) == PATH
