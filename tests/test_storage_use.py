"""The storage use of the database and the raw captures (#1235)."""

from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Capture, Trip
from app.retention import delete_old_captures
from app.storage import SourceUse, storage_use

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    eng = create_engine(empty_database_url)
    yield eng
    eng.dispose()


def _add(s: Session, source: str, size: int | None, age_days: int = 1) -> None:
    trip = s.query(Trip).first()
    if trip is None:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
    s.add(Capture(trip_id=trip.id, source=source, captured_at=NOW - timedelta(days=age_days),
                  raw_gz=None if size is None else b"x" * size))
    s.flush()


def test_sources_and_totals(engine):
    with Session(engine) as s:
        for size in (100, 200, None):
            _add(s, "bahn", size)
        _add(s, "flixbus", 50)
        use = storage_use(s, 90, NOW)
    assert use.sources == [SourceUse("bahn", 3, 300), SourceUse("flixbus", 1, 50)]
    assert use.captures == 4 and use.raw_bytes == 350
    assert use.database_bytes > 0


def test_cleanup_matches_delete_old_captures(engine):
    with Session(engine) as s:
        _add(s, "bahn", 70, age_days=40)
        _add(s, "bahn", 30, age_days=10)
        use = storage_use(s, 30, NOW)
        assert (use.cleanup_captures, use.cleanup_bytes) == (1, 70)
        none = storage_use(s, 0, NOW)
        assert (none.cleanup_captures, none.cleanup_bytes) == (0, 0)
        assert delete_old_captures(s, 30, NOW) == use.cleanup_captures
