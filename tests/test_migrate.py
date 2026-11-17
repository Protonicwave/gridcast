import psycopg
import pytest

from gridcast.migrate import apply_migrations, main

# The collector's role on the test database, which trusts loopback connections.
COLLECTOR_URL = "postgresql://gridcast_collector@127.0.0.1:5432/gridcast"


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
    empty_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRIDCAST_DATABASE_URL", empty_database)
    monkeypatch.delenv("GRIDCAST_COLLECTOR_PASSWORD", raising=False)
    assert main([]) == 0
    with psycopg.connect(empty_database, autocommit=True) as connection:
        # The role is shared by every database on the server, so undo any earlier run.
        connection.execute("alter role gridcast_collector nologin password null")
    with pytest.raises(psycopg.OperationalError, match="not permitted to log in"):
        psycopg.connect(COLLECTOR_URL).close()

    monkeypatch.setenv("GRIDCAST_COLLECTOR_PASSWORD", "it's-a-secret")
    assert main([]) == 0
    with psycopg.connect(COLLECTOR_URL) as connection:
        [(role,)] = connection.execute("select current_user").fetchall()
    with psycopg.connect(empty_database) as connection:
        [(stored,)] = connection.execute(
            "select rolpassword from pg_authid where rolname = 'gridcast_collector'"
        ).fetchall()
    assert role == "gridcast_collector"
    assert isinstance(stored, str)
    assert stored.startswith("SCRAM-SHA-256$")


def test_command_needs_the_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GRIDCAST_DATABASE_URL", raising=False)
    assert main([]) == 2
    assert "GRIDCAST_DATABASE_URL is not set" in capsys.readouterr().err
