"""Applies the archive's numbered SQL migrations, each once."""

import argparse
import logging
import os
import re
import sys
from collections.abc import Sequence
from importlib.resources import files
from typing import Any

import psycopg
from psycopg import sql

from gridcast.archive import CONNECT_TIMEOUT_SECONDS, DATABASE_URL_VARIABLE

EXIT_USAGE = 2
# S105 reads the variable's name as a password; the password is its value.
COLLECTOR_PASSWORD_VARIABLE = "GRIDCAST_COLLECTOR_PASSWORD"  # noqa: S105

# Any fixed key works, provided nothing else in the database takes the same advisory lock.
_LOCK_KEY = 0x6772_6964
_FILE_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")

log = logging.getLogger(__name__)


def apply_migrations(connection: psycopg.Connection[Any]) -> list[str]:
    """Apply, in version order, every migration not yet in schema_migration.

    Runs in one transaction under an advisory lock, so a failed migration leaves the
    database as it was and two concurrent runs apply each migration once. Returns the
    names applied.
    """
    applied_names: list[str] = []
    with connection.transaction():
        connection.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        connection.execute(
            "create table if not exists schema_migration (version smallint primary key,"
            " name text not null, applied_at timestamptz not null default now())"
        )
        applied = {row[0] for row in connection.execute("select version from schema_migration")}
        for version, name, statements in _migrations():
            if version in applied:
                continue
            connection.execute(statements)
            connection.execute(
                "insert into schema_migration (version, name) values (%s, %s)", (version, name)
            )
            applied_names.append(name)
    return applied_names


def _migrations() -> list[tuple[int, str, bytes]]:
    found: dict[int, tuple[int, str, bytes]] = {}
    for resource in (files("gridcast") / "migrations").iterdir():
        match = _FILE_NAME.fullmatch(resource.name)
        if match is None:
            raise RuntimeError(f"expected migrations named NNNN_name.sql, got {resource.name!r}")
        version = int(match.group(1))
        if version in found:
            raise RuntimeError(f"migration version {version} appears twice")
        found[version] = (version, resource.name, resource.read_bytes())
    return [found[version] for version in sorted(found)]


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(
        description=f"Apply pending migrations to the database at ${DATABASE_URL_VARIABLE}. "
        f"If ${COLLECTOR_PASSWORD_VARIABLE} is set, let the collector's role log in with it."
    ).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database_url = os.environ.get(DATABASE_URL_VARIABLE)
    if not database_url:
        print(f"gridcast-migrate: {DATABASE_URL_VARIABLE} is not set", file=sys.stderr)
        return EXIT_USAGE
    collector_password = os.environ.get(COLLECTOR_PASSWORD_VARIABLE)
    with psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as connection:
        applied_names = apply_migrations(connection)
        log.info("migrations applied count=%d names=%s", len(applied_names), applied_names)
        if collector_password:
            # The SCRAM verifier is computed here, so the password itself never reaches the
            # server, where a failed statement's text is logged. ALTER ROLE takes no bind
            # parameters, so the verifier goes in as a quoted literal.
            verifier = connection.pgconn.encrypt_password(
                collector_password.encode(), b"gridcast_collector", b"scram-sha-256"
            )
            connection.execute(
                sql.SQL("alter role gridcast_collector login password {}").format(
                    sql.Literal(verifier.decode())
                )
            )
            log.info("collector login enabled")
    return 0
