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

from gridcast.archive import CONNECT_TIMEOUT_SECONDS, DATABASE_URL_VARIABLE

EXIT_USAGE = 2

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
        description=f"Apply pending migrations to the database at ${DATABASE_URL_VARIABLE}."
    ).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database_url = os.environ.get(DATABASE_URL_VARIABLE)
    if not database_url:
        print(f"gridcast-migrate: {DATABASE_URL_VARIABLE} is not set", file=sys.stderr)
        return EXIT_USAGE
    with psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as connection:
        applied_names = apply_migrations(connection)
    log.info("migrations applied count=%d names=%s", len(applied_names), applied_names)
    return 0
