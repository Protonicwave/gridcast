import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from gridcast.migrate import apply_migrations

# The database compose.yaml runs, by address: on Windows "localhost" tries IPv6 first and
# waits for that to time out. Every test that uses it starts from an empty schema.
TEST_DATABASE_URL = "postgresql://gridcast@127.0.0.1:5432/gridcast"


@pytest.fixture
def empty_database() -> str:
    try:
        connection = psycopg.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as err:
        pytest.fail(
            f"no test database at {TEST_DATABASE_URL}; run `docker compose up -d db`: {err}"
        )
    with connection:
        connection.execute("drop schema public cascade")
        connection.execute("create schema public")
    return TEST_DATABASE_URL


@pytest.fixture
def archive(empty_database: str) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A connection to the empty, migrated archive."""
    with psycopg.connect(empty_database) as connection:
        apply_migrations(connection)
        yield connection


DOCKER_DESKTOP = Path("C:/Program Files/Docker/Docker/Docker Desktop.exe")
DOCKER_BIN_DIRECTORY = Path("C:/Program Files/Docker/Docker/resources/bin")
DOCKER_START_TIMEOUT_SECONDS = 180
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def pytest_sessionstart(session: pytest.Session) -> None:
    """Bring the test database up when it is not, so a bare `pytest` works on Windows.

    Starts Docker Desktop if its engine is down, then the compose database. Anything
    that cannot be done is left for the database fixture to report.
    """
    del session
    try:
        psycopg.connect(TEST_DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        _start_database()


def _start_database() -> None:
    docker = shutil.which("docker") or shutil.which("docker", path=str(DOCKER_BIN_DIRECTORY))
    if docker is None:
        return
    if not _docker_engine_is_up(docker):
        if sys.platform != "win32" or not DOCKER_DESKTOP.exists():
            return
        subprocess.Popen([str(DOCKER_DESKTOP)])  # noqa: S603
        deadline = time.monotonic() + DOCKER_START_TIMEOUT_SECONDS
        while not _docker_engine_is_up(docker):
            if time.monotonic() > deadline:
                return
            time.sleep(3)
    subprocess.run(  # noqa: S603
        [docker, "compose", "up", "-d", "--wait", "db"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        timeout=DOCKER_START_TIMEOUT_SECONDS,
    )


def _docker_engine_is_up(docker: str) -> bool:
    result = subprocess.run(  # noqa: S603
        [docker, "info"], check=False, capture_output=True, timeout=60
    )
    return result.returncode == 0
