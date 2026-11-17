import base64
import hashlib
import hmac

import psycopg
import pytest

from gridcast.migrate import apply_migrations, main

# The collector's role on the test database, which trusts loopback connections, so a
# connection proves the role may log in but not that its password is the one given.
COLLECTOR_URL = "postgresql://gridcast_collector@127.0.0.1:5432/gridcast"


def scram_verifier_matches(verifier: str, password: str) -> bool:
    """Whether a stored SCRAM-SHA-256 verifier was made from `password` (RFC 5802, 7677)."""
    mechanism, iterations_and_salt, keys = verifier.split("$")
    assert mechanism == "SCRAM-SHA-256"
    iterations, salt = iterations_and_salt.split(":")
    stored_key, server_key = (base64.b64decode(key) for key in keys.split(":"))
    salted = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), base64.b64decode(salt), int(iterations)
    )
    client_key = hmac.digest(salted, b"Client Key", "sha256")
    return (
        hashlib.sha256(client_key).digest() == stored_key
        and hmac.digest(salted, b"Server Key", "sha256") == server_key
    )


def collector_role(database_url: str) -> tuple[bool, str | None]:
    """Whether the collector's role may log in, and its stored password verifier."""
    with psycopg.connect(database_url) as connection:
        [(can_login, verifier)] = connection.execute(
            "select rolcanlogin, rolpassword from pg_authid where rolname = 'gridcast_collector'"
        ).fetchall()
    assert isinstance(can_login, bool)
    assert verifier is None or isinstance(verifier, str)
    return can_login, verifier


@pytest.fixture
def collector_without_login(empty_database: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """The migrated test database, with the collector's role unable to log in."""
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", empty_database)
    monkeypatch.delenv("GRIDCAST_COLLECTOR_PASSWORD", raising=False)
    assert main([]) == 0
    with psycopg.connect(empty_database, autocommit=True) as connection:
        # The role is shared by every database on the server, so undo any earlier run.
        connection.execute("alter role gridcast_collector nologin password null")
    return empty_database


def test_applies_each_migration_once(empty_database: str) -> None:
    with psycopg.connect(empty_database) as connection:
        assert apply_migrations(connection) == [
            "0001_create_archive.sql",
            "0002_national_feeds_and_views.sql",
        ]
        assert apply_migrations(connection) == []
        versions = connection.execute("select version from schema_migration").fetchall()
    assert versions == [(1,), (2,)]


def test_command_migrates_the_database_named_in_the_environment(
    empty_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", empty_database)
    assert main([]) == 0
    with psycopg.connect(empty_database) as connection:
        tables = connection.execute(
            "select tablename from pg_tables where schemaname = 'public' order by tablename"
        ).fetchall()
    assert tables == [
        ("api_fetch",),
        ("forecast_issue",),
        ("national_actual",),
        ("schema_migration",),
    ]


def test_command_lets_the_collector_log_in_with_the_password_it_is_given(
    collector_without_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(psycopg.OperationalError, match="not permitted to log in"):
        psycopg.connect(COLLECTOR_URL).close()

    monkeypatch.setenv("GRIDCAST_COLLECTOR_PASSWORD", "it's-a-secret")
    assert main([]) == 0
    with psycopg.connect(COLLECTOR_URL) as connection:
        [(role,)] = connection.execute("select current_user").fetchall()
    can_login, verifier = collector_role(collector_without_login)
    assert role == "gridcast_collector"
    assert can_login
    assert verifier is not None
    assert scram_verifier_matches(verifier, "it's-a-secret")
    assert not scram_verifier_matches(verifier, "another-secret")


def test_command_leaves_the_collector_without_login_when_the_password_is_empty(
    collector_without_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_COLLECTOR_PASSWORD", "")
    assert main([]) == 0
    assert collector_role(collector_without_login) == (False, None)


def test_command_needs_the_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GRIDCAST_DATABASE_URL", raising=False)
    assert main([]) == 2
    assert "GRIDCAST_DATABASE_URL is not set" in capsys.readouterr().err
