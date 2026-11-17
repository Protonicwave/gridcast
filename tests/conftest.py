from collections.abc import Iterator

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
