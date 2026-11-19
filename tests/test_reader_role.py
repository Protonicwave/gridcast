from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from test_archive import FETCHED_AT, OK, Archive, store
from test_migrate import scram_verifier_matches

from gridcast.archive import latest_issue
from gridcast.issues import StoredIssue
from gridcast.migrate import main

# The read-only role on the test database, which trusts loopback connections, so a
# connection proves the role may log in but not that its password is the one given.
READER_URL = "postgresql://gridcast_reader@127.0.0.1:5432/gridcast"


def reader_role(database_url: str) -> tuple[bool, str | None]:
    """Whether the reader's role may log in, and its stored password verifier."""
    with psycopg.connect(database_url) as connection:
        [(can_login, verifier)] = connection.execute(
            "select rolcanlogin, rolpassword from pg_authid where rolname = 'gridcast_reader'"
        ).fetchall()
    assert isinstance(can_login, bool)
    assert verifier is None or isinstance(verifier, str)
    return can_login, verifier


@pytest.fixture
def reader_without_login(empty_database: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """The migrated test database, with the reader's role unable to log in."""
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", empty_database)
    monkeypatch.delenv("GRIDCAST_COLLECTOR_PASSWORD", raising=False)
    monkeypatch.delenv("GRIDCAST_READER_PASSWORD", raising=False)
    assert main([]) == 0
    with psycopg.connect(empty_database, autocommit=True) as connection:
        # The role is shared by every database on the server, so undo any earlier run.
        connection.execute("alter role gridcast_reader nologin password null")
    return empty_database


def test_command_lets_the_reader_log_in_with_the_password_it_is_given(
    reader_without_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(psycopg.OperationalError, match="not permitted to log in"):
        psycopg.connect(READER_URL).close()

    monkeypatch.setenv("GRIDCAST_READER_PASSWORD", "it's-a-secret")
    assert main([]) == 0
    can_login, verifier = reader_role(reader_without_login)
    assert can_login
    assert verifier is not None
    assert scram_verifier_matches(verifier, "it's-a-secret")
    assert not scram_verifier_matches(verifier, "another-secret")


def test_command_leaves_the_reader_without_login_when_the_password_is_empty(
    reader_without_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_READER_PASSWORD", "")
    assert main([]) == 0
    assert reader_role(reader_without_login) == (False, None)


@pytest.fixture
def reader_url(archive: Archive) -> Iterator[str]:
    """The archive with one stored issue and a reader that may log in."""
    store(archive, OK, None, slots=2)
    archive.commit()
    archive.execute("alter role gridcast_reader login")
    archive.commit()
    yield READER_URL
    archive.execute("alter role gridcast_reader nologin")
    archive.commit()


def test_the_reader_can_read_the_newest_issue(reader_url: str) -> None:
    with psycopg.connect(reader_url) as connection:
        stored = latest_issue(connection, 13)
    assert stored == StoredIssue(
        first_slot=datetime(2026, 11, 17, 11, 30, tzinfo=UTC),
        intensities_g_per_kwh=(13, 14),
        fetched_at=FETCHED_AT,
    )


@pytest.mark.parametrize(
    "statement",
    [
        "insert into forecast_issue (feed, area_id, first_slot, fetch_id, intensities_g_per_kwh)"
        " values ('regional', 1, now(), 1, '{1}')",
        "update forecast_issue set area_id = 1",
        "delete from forecast_issue",
        "insert into national_actual (slot_start, fetch_id) values (now(), 1)",
        "select raw_gzip from api_fetch",
        "select error from api_fetch",
    ],
)
def test_the_reader_cannot_write_or_read_the_raw_responses(reader_url: str, statement: str) -> None:
    with (
        psycopg.connect(reader_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(statement)
