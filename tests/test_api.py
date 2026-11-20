import logging
from datetime import datetime, timedelta

import pytest
from factories import FIRST_SLOT
from fastapi.testclient import TestClient
from test_archive import OK, Archive, store

from gridcast.api import app_from_environment, create_app

ORIGIN = "https://pages.example.invalid"
# Twelve half hours from FIRST_SLOT: London's forecast is 13, 14, ... 24.
NOW = FIRST_SLOT + timedelta(minutes=40)
UNREACHABLE_URL = "postgresql://gridcast:hunter2@127.0.0.1:5432/no_such_database"


def client_for(database_url: str, now: datetime = NOW) -> TestClient:
    return TestClient(create_app(database_url, ORIGIN, lambda: now))


@pytest.fixture
def stored_url(archive: Archive) -> str:
    store(archive, OK, None, slots=12)
    archive.commit()
    return archive.info.dsn


def test_serves_the_outlook_in_the_documented_shape(stored_url: str) -> None:
    response = client_for(stored_url).get("/regions/13/outlook")
    assert response.status_code == 200
    assert response.json() == {
        "regionId": 13,
        "regionName": "London",
        "fetchedAt": "2026-11-17T11:50:00Z",
        "firstSlotStart": "2026-11-17T12:00Z",
        "slotMinutes": 30,
        "intensities": list(range(14, 25)),
        "windows": {
            str(hours): {
                "cleanest": {"start": 0, "mean": 13.5 + hours},
                "dirtiest": {"start": 11 - 2 * hours, "mean": 24.5 - hours},
                "timingMatters": False,
            }
            for hours in (1, 2, 3, 4)
        },
    }


def test_serves_every_region_in_id_order_with_the_single_region_body(stored_url: str) -> None:
    client = client_for(stored_url)
    response = client.get("/regions/outlook")
    assert response.status_code == 200
    bodies = response.json()
    assert [body["regionId"] for body in bodies] == list(range(1, 15))
    assert bodies[12] == client.get("/regions/13/outlook").json()
    assert response.headers["cache-control"] == "public, max-age=60"


def test_refuses_all_regions_when_one_has_no_forecast(archive: Archive) -> None:
    store(archive, OK, None, slots=12)
    archive.execute("delete from forecast_issue where area_id = 5")
    archive.commit()
    response = client_for(archive.info.dsn).get("/regions/outlook")
    assert response.status_code == 503
    assert "[5]" in response.json()["detail"]


def test_refuses_all_regions_when_one_has_no_half_hour_left(stored_url: str) -> None:
    response = client_for(stored_url, FIRST_SLOT + timedelta(hours=7)).get("/regions/outlook")
    assert response.status_code == 503


def test_lets_browsers_and_proxies_cache_for_a_minute(stored_url: str) -> None:
    response = client_for(stored_url).get("/regions/13/outlook")
    assert response.headers["cache-control"] == "public, max-age=60"


@pytest.mark.parametrize("region_id", ["0", "15", "-1"])
def test_refuses_a_region_outside_one_to_fourteen(stored_url: str, region_id: str) -> None:
    response = client_for(stored_url).get(f"/regions/{region_id}/outlook")
    assert response.status_code == 404
    assert region_id in response.json()["detail"]


def test_refuses_a_region_that_is_not_an_integer(stored_url: str) -> None:
    assert client_for(stored_url).get("/regions/london/outlook").status_code == 422


def test_reports_no_forecast_for_an_empty_archive(archive: Archive) -> None:
    response = client_for(archive.info.dsn).get("/regions/13/outlook")
    assert response.status_code == 503
    assert "no forecast" in response.json()["detail"]


def test_reports_an_issue_with_no_half_hour_left(stored_url: str) -> None:
    response = client_for(stored_url, FIRST_SLOT + timedelta(hours=7)).get("/regions/13/outlook")
    assert response.status_code == 503
    assert "no half hour left" in response.json()["detail"]


def test_reports_a_refused_connection_without_leaking_its_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        response = client_for(UNREACHABLE_URL).get("/regions/13/outlook")
    assert response.status_code == 503
    logged = [record for record in caplog.records if record.name == "gridcast.api"]
    assert len(logged) == 1
    for text in (response.text, logged[0].getMessage()):
        assert "hunter2" not in text
        assert "127.0.0.1" not in text
    assert "OperationalError" in logged[0].getMessage()


def test_allows_the_configured_origin_only(stored_url: str) -> None:
    client = client_for(stored_url)
    allowed = client.get("/regions/13/outlook", headers={"Origin": ORIGIN})
    other = client.get("/regions/13/outlook", headers={"Origin": "https://other.example.invalid"})
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-origin" not in other.headers


def test_is_configured_from_the_environment(
    stored_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", stored_url)
    monkeypatch.setenv("GRIDCAST_ALLOWED_ORIGIN", ORIGIN)
    app = app_from_environment()
    assert TestClient(app).get("/regions/99/outlook").status_code == 404


@pytest.mark.parametrize("missing", ["GRIDCAST_DATABASE_URL", "GRIDCAST_ALLOWED_ORIGIN"])
def test_names_the_variable_that_is_not_set(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", "postgresql://example.invalid/gridcast")
    monkeypatch.setenv("GRIDCAST_ALLOWED_ORIGIN", ORIGIN)
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        app_from_environment()


def test_refuses_all_regions_when_one_covers_different_half_hours(archive: Archive) -> None:
    store(archive, OK, None, slots=12)
    archive.execute(
        "update forecast_issue set first_slot = first_slot - interval '1 hour' where area_id = 5"
    )
    archive.commit()
    response = client_for(archive.info.dsn).get("/regions/outlook")
    assert response.status_code == 503
    assert "different half hours" in response.json()["detail"]
