import gzip
import json
import time
import urllib.request
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from factories import national_payload
from fakes import FakeResponse, FakeServer, http_error

from gridcast.collect import main
from gridcast.forecast import TIME_FORMAT

SAVED_RESPONSE = Path(__file__).parent.parent / "data" / "regional_fw48h_20261117T1150Z.json"
UNREACHABLE_DATABASE_URL = "postgresql://gridcast@127.0.0.1:1/gridcast"
HEALTHCHECK_URL = "https://hc-ping.example/5f0c1d2e"

Archive = psycopg.Connection[tuple[object, ...]]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def no_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRIDCAST_HEALTHCHECK_URL", raising=False)


def json_response(data: object) -> FakeResponse:
    return FakeResponse(json.dumps(data).encode())


def good_national_forecast() -> FakeResponse:
    return json_response(national_payload(150, None))


def good_national_actuals() -> FakeResponse:
    return json_response(national_payload(150, 160, None))


def collect(
    monkeypatch: pytest.MonkeyPatch, database_url: str, *answers: FakeResponse | Exception
) -> int:
    """Run the collector with `answers` for the regional call, then good national calls."""
    return collect_all(
        monkeypatch, database_url, *answers, good_national_forecast(), good_national_actuals()
    )


def collect_all(
    monkeypatch: pytest.MonkeyPatch, database_url: str, *answers: FakeResponse | Exception
) -> int:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", database_url)
    server = FakeServer(*answers)
    monkeypatch.setattr(urllib.request, "urlopen", server.urlopen)
    status = main([])
    assert not server.outcomes, "the collector left scripted answers unused"
    return status


def fetches(archive: Archive, endpoint: str = "regional_forecast") -> list[tuple[object, ...]]:
    archive.commit()
    return archive.execute(
        "select endpoint, http_status, attempts, raw_gzip, error from api_fetch"
        " where endpoint = %s order by fetch_id",
        (endpoint,),
    ).fetchall()


def issue_count(archive: Archive, feed: str = "regional") -> int:
    archive.commit()
    [(count,)] = archive.execute(
        "select count(*) from forecast_issue where feed = %s", (feed,)
    ).fetchall()
    assert isinstance(count, int)
    return count


def test_stores_the_fetch_with_its_raw_body_and_one_issue_per_area(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = SAVED_RESPONSE.read_bytes()
    assert collect(monkeypatch, archive.info.dsn, FakeResponse(body)) == 0
    [(endpoint, status, attempts, raw_gzip, error)] = fetches(archive)
    assert (endpoint, status, attempts, error) == ("regional_forecast", 200, 1, None)
    assert isinstance(raw_gzip, bytes)
    assert gzip.decompress(raw_gzip) == body
    stored = archive.execute(
        "select area_id, first_slot, intensities_g_per_kwh from forecast_issue"
        " where feed = 'regional' order by area_id"
    ).fetchall()
    assert [row[0] for row in stored] == list(range(1, 19))
    south_wales = stored[6][2]
    assert isinstance(south_wales, list)
    assert (len(south_wales), south_wales[0]) == (96, 281)


def test_a_second_run_in_the_same_half_hour_adds_a_fetch_and_no_issues(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = SAVED_RESPONSE.read_bytes()
    assert collect(monkeypatch, archive.info.dsn, FakeResponse(body)) == 0
    assert collect(monkeypatch, archive.info.dsn, FakeResponse(body)) == 0
    assert len(fetches(archive)) == 2
    assert issue_count(archive) == 18


def test_stores_an_unparseable_body_raw_with_its_error(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert collect(monkeypatch, archive.info.dsn, FakeResponse(b"<html>busy</html>")) == 1
    [(_, status, _, raw_gzip, error)] = fetches(archive)
    assert status == 200
    assert isinstance(raw_gzip, bytes)
    assert gzip.decompress(raw_gzip) == b"<html>busy</html>"
    assert isinstance(error, str)
    assert error.startswith("body is not JSON")
    assert issue_count(archive) == 0


def test_stores_a_body_of_the_wrong_shape_raw_with_the_offending_value(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert collect(monkeypatch, archive.info.dsn, FakeResponse(b'{"data": []}')) == 1
    [(_, _, _, raw_gzip, error)] = fetches(archive)
    assert raw_gzip is not None
    assert error == "data holds no slots"
    assert issue_count(archive) == 0


def test_records_a_failed_fetch_without_a_body(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert collect(monkeypatch, archive.info.dsn, http_error(404)) == 1
    assert fetches(archive) == [("regional_forecast", 404, 1, None, "HTTP 404 Reason")]


def test_records_the_attempts_a_retried_fetch_took(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = (http_error(503), TimeoutError("timed out"), TimeoutError("timed out"))
    assert collect(monkeypatch, archive.info.dsn, *answers) == 1
    [(_, status, attempts, raw_gzip, error)] = fetches(archive)
    assert (status, attempts, raw_gzip, error) == (None, 3, None, "TimeoutError: timed out")


def test_fails_without_calling_the_api_when_the_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", UNREACHABLE_DATABASE_URL)
    server = FakeServer()
    monkeypatch.setattr(urllib.request, "urlopen", server.urlopen)
    assert main([]) == 1
    assert server.requests == []


def test_needs_the_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GRIDCAST_DATABASE_URL", raising=False)
    assert main([]) == 2
    assert "GRIDCAST_DATABASE_URL is not set" in capsys.readouterr().err


def test_stores_the_national_forecast_and_actuals_beside_the_regional_forecast(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert collect(monkeypatch, archive.info.dsn, FakeResponse(SAVED_RESPONSE.read_bytes())) == 0
    assert fetches(archive, "national_forecast")[0][:3] == ("national_forecast", 200, 1)
    assert fetches(archive, "national_actual")[0][:3] == ("national_actual", 200, 1)
    assert issue_count(archive, "national") == 1
    stored = archive.execute(
        "select intensity_g_per_kwh from national_actual order by slot_start"
    ).fetchall()
    assert stored == [(150,), (160,), (None,)]


def test_asks_for_the_last_day_of_actuals(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", archive.info.dsn)
    server = FakeServer(
        FakeResponse(SAVED_RESPONSE.read_bytes()), good_national_forecast(), good_national_actuals()
    )
    monkeypatch.setattr(urllib.request, "urlopen", server.urlopen)
    main([])
    [regional, national, actuals] = [url for url, _ in server.requests]
    prefix = "https://api.carbonintensity.org.uk/intensity/"
    assert regional.endswith("/fw48h")
    assert national.startswith(prefix)
    assert national.endswith("/fw48h")
    start, end = actuals.removeprefix(prefix).split("/")
    elapsed = datetime.strptime(end, TIME_FORMAT) - datetime.strptime(start, TIME_FORMAT)
    assert elapsed == timedelta(hours=24)


def test_a_failed_national_call_does_not_lose_the_regional_forecast(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = collect_all(
        monkeypatch,
        archive.info.dsn,
        FakeResponse(SAVED_RESPONSE.read_bytes()),
        http_error(404),
        good_national_actuals(),
    )
    assert status == 1
    assert issue_count(archive) == 18
    assert fetches(archive, "national_forecast") == [
        ("national_forecast", 404, 1, None, "HTTP 404 Reason")
    ]
    assert fetches(archive, "national_actual")[0][4] is None


def test_stores_a_malformed_national_body_raw_with_its_error(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = collect_all(
        monkeypatch,
        archive.info.dsn,
        FakeResponse(SAVED_RESPONSE.read_bytes()),
        good_national_forecast(),
        FakeResponse(b'{"data": []}'),
    )
    assert status == 1
    [(_, _, _, raw_gzip, error)] = fetches(archive, "national_actual")
    assert raw_gzip is not None
    assert error == "data holds no slots"


def collect_with_health_check(
    monkeypatch: pytest.MonkeyPatch, database_url: str, *answers: FakeResponse | Exception
) -> tuple[int, list[str]]:
    """Run the collector with the health check configured; return its status and the URLs asked."""
    monkeypatch.setenv("GRIDCAST_HEALTHCHECK_URL", HEALTHCHECK_URL)
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", database_url)
    server = FakeServer(*answers)
    monkeypatch.setattr(urllib.request, "urlopen", server.urlopen)
    status = main([])
    assert not server.outcomes, "the collector left scripted answers unused"
    return status, [url for url, _ in server.requests]


def test_pings_the_health_check_once_the_regional_forecast_is_stored(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, urls = collect_with_health_check(
        monkeypatch,
        archive.info.dsn,
        FakeResponse(SAVED_RESPONSE.read_bytes()),
        good_national_forecast(),
        good_national_actuals(),
        FakeResponse(b"OK"),
    )
    assert status == 0
    assert urls[-1] == HEALTHCHECK_URL
    assert issue_count(archive) == 18


def test_does_not_ping_the_health_check_when_the_regional_forecast_failed(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, urls = collect_with_health_check(
        monkeypatch,
        archive.info.dsn,
        http_error(404),
        good_national_forecast(),
        good_national_actuals(),
    )
    assert status == 1
    assert HEALTHCHECK_URL not in urls


@pytest.mark.parametrize(
    "ping_answer", [http_error(500), TimeoutError("timed out")], ids=["http-500", "timeout"]
)
def test_a_failed_ping_leaves_the_run_successful(
    archive: Archive, monkeypatch: pytest.MonkeyPatch, ping_answer: Exception
) -> None:
    status, urls = collect_with_health_check(
        monkeypatch,
        archive.info.dsn,
        FakeResponse(SAVED_RESPONSE.read_bytes()),
        good_national_forecast(),
        good_national_actuals(),
        ping_answer,
    )
    assert status == 0
    assert urls.count(HEALTHCHECK_URL) == 1


def test_pings_the_health_check_when_only_a_national_call_failed(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, urls = collect_with_health_check(
        monkeypatch,
        archive.info.dsn,
        FakeResponse(SAVED_RESPONSE.read_bytes()),
        http_error(404),
        good_national_actuals(),
        FakeResponse(b"OK"),
    )
    assert status == 1
    assert urls[-1] == HEALTHCHECK_URL


def test_an_empty_health_check_url_means_no_ping(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_HEALTHCHECK_URL", "")
    body = SAVED_RESPONSE.read_bytes()
    assert (
        collect_all(
            monkeypatch,
            archive.info.dsn,
            FakeResponse(body),
            good_national_forecast(),
            good_national_actuals(),
        )
        == 0
    )


def test_a_ping_url_the_network_layer_rejects_leaves_the_run_successful(
    archive: Archive, monkeypatch: pytest.MonkeyPatch
) -> None:
    """urlopen raises UnicodeError, a ValueError, for a host with an empty label."""
    body = SAVED_RESPONSE.read_bytes()
    server = FakeServer(FakeResponse(body), good_national_forecast(), good_national_actuals())

    def answer_or_reject(
        request: urllib.request.Request, timeout: float
    ) -> AbstractContextManager[FakeResponse]:
        if request.full_url == "https://a..b/ping":
            raise UnicodeError("label empty or too long")
        return server.urlopen(request, timeout)

    monkeypatch.setenv("GRIDCAST_DATABASE_URL", archive.info.dsn)
    monkeypatch.setenv("GRIDCAST_HEALTHCHECK_URL", "https://a..b/ping")
    monkeypatch.setattr(urllib.request, "urlopen", answer_or_reject)
    assert main([]) == 0
    assert not server.outcomes


@pytest.mark.parametrize(
    "healthcheck_url",
    ["http://hc-ping.example/5f0c1d2e", "https:///5f0c1d2e", "hc-ping.example/5f0c1d2e"],
    ids=["http", "no-host", "no-scheme"],
)
def test_refuses_a_health_check_url_that_is_not_https_with_a_host(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], healthcheck_url: str
) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("GRIDCAST_HEALTHCHECK_URL", healthcheck_url)
    server = FakeServer()
    monkeypatch.setattr(urllib.request, "urlopen", server.urlopen)
    assert main([]) == 2
    error = capsys.readouterr().err
    assert "GRIDCAST_HEALTHCHECK_URL must be an https URL with a host" in error
    assert "5f0c1d2e" not in error
    assert server.requests == []
