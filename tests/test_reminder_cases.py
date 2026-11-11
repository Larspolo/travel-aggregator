"""The cases of the "Search again" reminder rule (#1116, #1135): due_reminders and the daily step.

A reminder sends no request to a travel site (P1): the test of the daily step records every socket connect."""

import socket
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app import backup, notify, reminder
from app.models import Capture, Itinerary, Setting, Trip
from app.reminder import due_reminders

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)
NTFY = "https://ntfy.example/topic"


def _trip(s: Session, title: str, in_days: int, searched_days_ago: int | None = None,
          reminded_days_ago: int | None = None) -> Trip:
    """A pinned trip that departs in `in_days` days. `searched_days_ago=None`: no capture at all."""
    trip = Trip(title=title, date_from=NOW.date() + timedelta(days=in_days), status="planning",
                reminded_at=None if reminded_days_ago is None else NOW - timedelta(days=reminded_days_ago))
    s.add(trip)
    s.flush()
    depart = NOW + timedelta(days=in_days)
    s.add(Itinerary(trip_id=trip.id, fingerprint=f"f{trip.id}", depart_at=depart,
                    arrive_at=depart + timedelta(hours=1), duration_min=60, pinned=True))
    if searched_days_ago is not None:
        s.add(Capture(trip_id=trip.id, source="ns", captured_at=NOW - timedelta(days=searched_days_ago)))
    s.flush()
    return trip


def _settings(s: Session, n: str = "3", d: str = "14") -> None:
    s.merge(Setting(key=reminder.REMINDER_DAYS_KEY, value=n))
    s.merge(Setting(key=reminder.REMINDER_BEFORE_KEY, value=d))


def _titles(s: Session) -> list[str]:
    return [t.title for t in due_reminders(s, NOW)]


@pytest.fixture
def engine(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    eng = create_engine(empty_database_url)
    yield eng
    eng.dispose()


def test_a_trip_searched_one_day_ago_is_not_due_even_when_reminded_four_days_ago(engine):
    with Session(engine) as s:
        _settings(s, n="3")
        _trip(s, "fresh search", 10, searched_days_ago=1, reminded_days_ago=4)
        assert _titles(s) == []


def test_a_trip_never_searched_that_departs_in_ten_days_is_due(engine):
    with Session(engine) as s:
        _settings(s, n="3", d="14")
        _trip(s, "never searched", 10, searched_days_ago=None)
        assert _titles(s) == ["never searched"]


def test_a_trip_departing_today_is_due(engine):
    with Session(engine) as s:
        _settings(s, n="3", d="14")
        _trip(s, "today", 0, searched_days_ago=None)
        assert _titles(s) == ["today"]


def test_a_trip_departing_in_exactly_d_days_is_due_and_d_plus_one_is_not(engine):
    with Session(engine) as s:
        _settings(s, n="3", d="14")
        _trip(s, "at D", 14, searched_days_ago=None)
        _trip(s, "at D plus one", 15, searched_days_ago=None)
        assert _titles(s) == ["at D"]


@pytest.fixture
def setup(monkeypatch, sessions, tmp_path):
    with sessions() as s:
        for key, value in [(notify.CHANNEL_KEY, "ntfy"), (notify.NTFY_URL_KEY, NTFY),
                           (notify.REMINDER_DAYS_KEY, "3"), (reminder.BASE_URL_KEY, "https://travel.example/")]:
            s.merge(Setting(key=key, value=value))
        trip = Trip(title="Lisbon week", origin_text="Amsterdam", destination_text="Lisbon", status="planning",
                    date_from=NOW.date() + timedelta(days=5))
        s.add(trip)
        s.flush()
        depart = NOW + timedelta(days=5)
        s.add(Itinerary(trip_id=trip.id, fingerprint="f-lisbon", depart_at=depart,
                        arrive_at=depart + timedelta(hours=3), duration_min=180, pinned=True))
        s.commit()
    posts = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: posts.append((url, headers["Title"], text)))
    monkeypatch.setattr(notify, "send_email", lambda m: posts.append(("email", m)))
    monkeypatch.setattr(notify, "push", lambda m: posts.append(("push", m)))
    monkeypatch.setattr(backup, "dump", lambda u, d, kind: None)
    monkeypatch.setattr(backup, "_check_step", lambda u, path, now: None)
    connects = []

    def refuse(*args, **kwargs):
        connects.append(args)
        raise OSError("no network in a test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return posts, connects


def test_one_daily_step_with_a_due_trip_calls_only_the_ntfy_post(migrated_url, setup, tmp_path):
    posts, connects = setup
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    assert len(posts) == 1
    url, title, text = posts[0]
    assert url == NTFY
    assert title == "Search again: Lisbon week"
    assert "https://" in text
    assert connects == []
