"""The trips that need a new search (#1118): due_reminders and mark_reminded; the migration 0022."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models import Capture, Itinerary, Setting, Trip
from app.notify import REMINDER_BEFORE_KEY, REMINDER_DAYS_KEY
from app.reminder import due_reminders, mark_reminded

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def _alembic(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def engine(empty_database_url):
    command.upgrade(_alembic(empty_database_url), "head")
    eng = create_engine(empty_database_url)
    yield eng
    eng.dispose()


def _trip(s: Session, title: str, in_days: int, searched_days_ago: int, pin: bool = True, target=None,
          status: str = "planning", reminded_days_ago=None) -> Trip:
    trip = Trip(title=title, date_from=NOW.date() + timedelta(days=in_days), status=status, target_price=target,
                reminded_at=None if reminded_days_ago is None else NOW - timedelta(days=reminded_days_ago))
    s.add(trip)
    s.flush()
    depart = NOW + timedelta(days=in_days)
    s.add(Itinerary(trip_id=trip.id, fingerprint=f"f{trip.id}", depart_at=depart, arrive_at=depart + timedelta(hours=1),
                    duration_min=60, pinned=pin))
    s.add(Capture(trip_id=trip.id, source="ns", captured_at=NOW - timedelta(days=searched_days_ago)))
    s.flush()
    return trip


def _settings(s: Session, n: str = "3", d: str = "14") -> None:
    s.merge(Setting(key=REMINDER_DAYS_KEY, value=n))
    s.merge(Setting(key=REMINDER_BEFORE_KEY, value=d))


def _titles(s: Session) -> list[str]:
    return [t.title for t in due_reminders(s, NOW)]


def test_only_a_pinned_near_stale_trip_is_due(engine):
    with Session(engine) as s:
        _settings(s)
        _trip(s, "due", 10, 4)
        _trip(s, "fresh", 10, 2)
        _trip(s, "far", 20, 4)
        _trip(s, "past", -1, 4)
        _trip(s, "archived", 10, 4, status="archived")
        _trip(s, "no pin", 10, 4, pin=False)
        _trip(s, "target", 10, 4, pin=False, target=Decimal("80"))
        assert _titles(s) == ["due", "target"]


def test_a_recent_reminder_waits_n_days(engine):
    with Session(engine) as s:
        _settings(s)
        _trip(s, "recent", 10, 4, reminded_days_ago=1)
        old = _trip(s, "old", 10, 4, reminded_days_ago=4)
        assert _titles(s) == ["old"]
        mark_reminded(old, NOW)
        s.flush()
        assert old.reminded_at == NOW
        assert _titles(s) == []


def test_n_zero_turns_the_reminders_off(engine):
    with Session(engine) as s:
        _settings(s, n="0")
        _trip(s, "due", 10, 4)
        assert _titles(s) == []


def test_the_migration_downgrades_and_upgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0021")
    eng = create_engine(empty_database_url)
    assert "reminded_at" not in {c["name"] for c in inspect(eng).get_columns("trips")}
    command.upgrade(cfg, "head")
    assert "reminded_at" in {c["name"] for c in inspect(eng).get_columns("trips")}
    eng.dispose()
