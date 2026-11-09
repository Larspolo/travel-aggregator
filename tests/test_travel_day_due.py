"""The travel-day messages (#1648): due_travel_days, mark_sent and the migration 0034."""

from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models import Itinerary, Setting, Trip
from app.travel_day import TRAVEL_DAY_HOURS_KEY, due_travel_days, mark_sent

DEPART = datetime(2026, 12, 1, 7, 15, tzinfo=timezone.utc)


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


def _itin(s: Session, title: str, booked: bool = True, sent=None, status: str = "planning",
          depart: datetime = DEPART) -> Itinerary:
    trip = Trip(title=title, date_from=depart.date(), status=status)
    s.add(trip)
    s.flush()
    it = Itinerary(trip_id=trip.id, fingerprint=f"f{trip.id}", depart_at=depart,
                   arrive_at=depart + timedelta(hours=1), duration_min=60, booked=booked,
                   travel_day_sent_at=sent)
    s.add(it)
    s.flush()
    return it


def _hours(s: Session, h: str = "24") -> None:
    s.merge(Setting(key=TRAVEL_DAY_HOURS_KEY, value=h))


def _titles(s: Session, now: datetime) -> list[str]:
    return [it.trip.title for it in due_travel_days(s, now)]


def test_due_only_within_h_hours_before_departure(engine):
    with Session(engine) as s:
        _hours(s)
        _itin(s, "due")
        assert _titles(s, datetime(2026, 11, 30, 7, 15, tzinfo=timezone.utc)) == ["due"]
        assert _titles(s, datetime(2026, 12, 1, 7, 0, tzinfo=timezone.utc)) == ["due"]
        assert _titles(s, datetime(2026, 11, 30, 7, 0, tzinfo=timezone.utc)) == []
        assert _titles(s, DEPART) == []
        assert _titles(s, datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)) == []


def test_unbooked_sent_and_archived_are_not_due(engine):
    with Session(engine) as s:
        _hours(s)
        _itin(s, "unbooked", booked=False)
        _itin(s, "sent", sent=datetime(2026, 11, 30, 8, 0, tzinfo=timezone.utc))
        _itin(s, "archived", status="archived")
        _itin(s, "due")
        assert _titles(s, datetime(2026, 11, 30, 7, 15, tzinfo=timezone.utc)) == ["due"]


def test_h_zero_turns_the_messages_off(engine):
    with Session(engine) as s:
        _hours(s, "0")
        _itin(s, "due")
        assert _titles(s, datetime(2026, 11, 30, 7, 15, tzinfo=timezone.utc)) == []


def test_a_bad_setting_counts_as_zero(engine):
    with Session(engine) as s:
        _hours(s, "soon")
        _itin(s, "due")
        assert _titles(s, datetime(2026, 11, 30, 7, 15, tzinfo=timezone.utc)) == []


def test_mark_sent_stops_the_message(engine):
    with Session(engine) as s:
        _hours(s)
        it = _itin(s, "due")
        now = datetime(2026, 11, 30, 7, 15, tzinfo=timezone.utc)
        mark_sent(it, now)
        s.flush()
        assert it.travel_day_sent_at == now
        assert _titles(s, now) == []


def test_the_migration_downgrades_and_upgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0033")
    eng = create_engine(empty_database_url)
    assert "travel_day_sent_at" not in {c["name"] for c in inspect(eng).get_columns("itineraries")}
    command.upgrade(cfg, "head")
    assert "travel_day_sent_at" in {c["name"] for c in inspect(eng).get_columns("itineraries")}
    eng.dispose()
