from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from test_archive import Archive, store_actuals
from test_reader_role import READER_URL

from gridcast.archive import national_actuals


@pytest.fixture
def reader_url(archive: Archive) -> Iterator[str]:
    """The archive with two stored actuals, one missing, and a reader that may log in."""
    store_actuals(archive, 150, None, 170)
    archive.execute("alter role gridcast_reader login")
    archive.commit()
    yield READER_URL
    archive.execute("alter role gridcast_reader nologin")
    archive.commit()


def test_the_reader_can_read_the_national_actuals(reader_url: str) -> None:
    with psycopg.connect(reader_url) as connection:
        found = national_actuals(
            connection, datetime(2026, 11, 17, tzinfo=UTC), datetime(2026, 11, 18, tzinfo=UTC)
        )
    assert found == {
        datetime(2026, 11, 17, 11, 30, tzinfo=UTC): 150,
        datetime(2026, 11, 17, 12, 30, tzinfo=UTC): 170,
    }


@pytest.mark.parametrize(
    "statement",
    [
        "select fetch_id from national_actual",
        "update national_actual set intensity_g_per_kwh = 1",
        "delete from national_actual",
    ],
)
def test_the_reader_can_neither_see_the_fetch_nor_change_an_actual(
    reader_url: str, statement: str
) -> None:
    with (
        psycopg.connect(reader_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(statement)
