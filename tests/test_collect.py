import gzip
import time
import urllib.request
from pathlib import Path

import psycopg
import pytest
from fakes import FakeResponse, FakeServer, http_error

from gridcast.collect import main

SAVED_RESPONSE = Path(__file__).parent.parent / "data" / "regional_fw48h_20261117T1150Z.json"
UNREACHABLE_DATABASE_URL = "postgresql://gridcast@127.0.0.1:1/gridcast"

Archive = psycopg.Connection[tuple[object, ...]]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


def collect(
    monkeypatch: pytest.MonkeyPatch, database_url: str, *answers: FakeResponse | Exception
) -> int:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", database_url)
    monkeypatch.setattr(urllib.request, "urlopen", FakeServer(*answers).urlopen)
    return main([])


def fetches(archive: Archive) -> list[tuple[object, ...]]:
    archive.commit()
    return archive.execute(
        "select endpoint, http_status, attempts, raw_gzip, error from api_fetch order by fetch_id"
    ).fetchall()


def issue_count(archive: Archive) -> int:
    archive.commit()
    [(count,)] = archive.execute("select count(*) from forecast_issue").fetchall()
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
        "select area_id, first_slot, intensities_g_per_kwh from forecast_issue order by area_id"
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


def test_fails_when_the_database_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    body = SAVED_RESPONSE.read_bytes()
    assert collect(monkeypatch, UNREACHABLE_DATABASE_URL, FakeResponse(body)) == 1


def test_needs_the_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GRIDCAST_DATABASE_URL", raising=False)
    assert main([]) == 2
    assert "GRIDCAST_DATABASE_URL is not set" in capsys.readouterr().err
