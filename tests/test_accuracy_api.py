import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_archive import OK, Archive
from test_reader_role import READER_URL

from gridcast.api import create_app
from gridcast.archive import store_fetch
from gridcast.carbon_api import FetchResult
from gridcast.issues import Actual, Issue, Parsed

ORIGIN = "https://pages.example.invalid"
DAY = date(2026, 11, 18)
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
HALF_HOUR = timedelta(minutes=30)
# London-sized error for every pair: forecasts sit this far above the actuals.
ERROR = 3
ACTUAL = 200
UNREACHABLE_URL = "postgresql://gridcast:hunter2@127.0.0.1:5432/no_such_database"


def client_for(database_url: str) -> TestClient:
    return TestClient(create_app(database_url, ORIGIN, lambda: NOW))


def store_usable_day(archive: Archive, day: date) -> None:
    """Forecasts fetched every half hour from 48 h before the day to its end, and its actuals."""
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    for fetch in range(-96, 48):
        first_slot = midnight + HALF_HOUR * fetch
        result = FetchResult(
            "https://example.invalid/",
            first_slot + timedelta(minutes=5),
            200,
            b"{}",
            None,
            1,
            120,
        )
        issue = Issue("national", 18, first_slot, (ACTUAL + ERROR,) * 96)
        store_fetch(
            archive,
            endpoint="national_forecast",
            result=result,
            error=None,
            parsed=Parsed(issues=(issue,)),
        )
    store_fetch(
        archive,
        endpoint="national_actual",
        result=OK,
        error=None,
        parsed=Parsed(
            actuals=tuple(Actual(midnight + HALF_HOUR * step, ACTUAL) for step in range(48))
        ),
    )
    archive.commit()


@pytest.fixture
def usable_day_url(archive: Archive) -> str:
    store_usable_day(archive, DAY)
    return archive.info.dsn


def test_serves_the_error_by_band_in_the_documented_shape(usable_day_url: str) -> None:
    response = client_for(usable_day_url).get("/accuracy/national")
    assert response.status_code == 200
    assert response.json() == {
        "until": "2026-11-20",
        "bands": [
            {
                "fromHours": start,
                "toHours": end,
                "pairs": pairs,
                "maeGPerKwh": ERROR,
                "interval": None,
            }
            for (start, end), pairs in zip(
                [(1, 6), (6, 12), (12, 24), (24, 48)], [480, 576, 1152, 2256], strict=True
            )
        ],
        "difference": {"maeGPerKwh": 0, "interval": None},
        "days": {"usable": ["2026-11-18"], "excluded": []},
    }


def test_lets_browsers_and_proxies_cache_for_half_an_hour(usable_day_url: str) -> None:
    response = client_for(usable_day_url).get("/accuracy/national")
    assert response.headers["cache-control"] == "public, max-age=1800"


def test_answers_an_empty_archive_with_no_days_and_no_error(archive: Archive) -> None:
    body = client_for(archive.info.dsn).get("/accuracy/national").json()
    assert body["days"] == {"usable": [], "excluded": []}
    assert body["difference"] == {"maeGPerKwh": None, "interval": None}
    assert {band["maeGPerKwh"] for band in body["bands"]} == {None}


def test_stops_before_the_day_named_by_until(usable_day_url: str) -> None:
    body = (
        client_for(usable_day_url).get("/accuracy/national", params={"until": "2026-11-18"}).json()
    )
    assert body["until"] == "2026-11-18"
    assert body["days"] == {"usable": [], "excluded": []}


def test_never_reads_the_day_under_way_whatever_until_says(usable_day_url: str) -> None:
    body = (
        client_for(usable_day_url).get("/accuracy/national", params={"until": "2030-01-01"}).json()
    )
    assert body["until"] == "2026-11-20"
    assert body["days"]["usable"] == ["2026-11-18"]


@pytest.mark.parametrize("until", ["yesterday", "2026-13-01", "1999-12-31", "0001-01-01"])
def test_refuses_an_until_that_is_not_a_plausible_date(usable_day_url: str, until: str) -> None:
    response = client_for(usable_day_url).get("/accuracy/national", params={"until": until})
    assert response.status_code == 422


def test_reports_a_refused_connection_without_leaking_its_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        response = client_for(UNREACHABLE_URL).get("/accuracy/national")
    assert response.status_code == 503
    assert "hunter2" not in response.text
    assert "hunter2" not in caplog.text


@pytest.fixture
def reader_url(usable_day_url: str, archive: Archive) -> Iterator[str]:
    archive.execute("alter role gridcast_reader login")
    archive.commit()
    yield READER_URL
    archive.execute("alter role gridcast_reader nologin")
    archive.commit()


def test_is_served_with_nothing_more_than_the_readers_privileges(reader_url: str) -> None:
    response = client_for(reader_url).get("/accuracy/national")
    assert response.status_code == 200
    assert response.json()["days"]["usable"] == ["2026-11-18"]
