"""The results pages with no offers seen (#1755): POST /api/silent, the status per source and the retention."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, SilentPage, Trip
from app.retention import delete_old_captures
from tests.test_trip_booked import _alembic

PASSWORD = "pw"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def token(sessions):
    with sessions() as s:
        return tokens.create(s, "t")


def body(**kw):
    return {"source": "bahn.de", "page_url": "https://www.bahn.de/buchung/fahrplan/suche?so=A#x",
            "seen_at": (T0 + timedelta(minutes=4)).isoformat(), "script_version": "1.2.0", **kw}


def silent(token, **kw):
    return TestClient(app).post("/api/silent", json=body(**kw), headers={"Authorization": f"Bearer {token}"})


def test_post_stores_one_row(sessions, token):
    assert silent(token).status_code == 200
    with sessions() as s:
        rows = s.scalars(select(SilentPage)).all()
    assert len(rows) == 1
    assert rows[0].page_url == "/buchung/fahrplan/suche?so=A"
    assert rows[0].seen_at == T0 + timedelta(minutes=4)


def test_bad_token_and_bad_values(sessions, token):
    assert silent("wrong").status_code == 401
    assert silent(token, source="example.com").status_code == 422
    assert silent(token, seen_at="2026-11-01T12:00:00").status_code == 422
    assert silent(token, cookie="x").status_code == 422
    with sessions() as s:
        assert s.scalars(select(SilentPage)).all() == []


def _page(c):
    return c.get("/captures").text


def test_captures_page_shows_the_silent_pages(sessions, token, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        trip_id = trip.id
        s.add(Capture(trip_id=trip_id, source="bahn.de", parser_version="1.2.0", captured_at=T0, offer_count=3,
                      rejected_count=0))
        s.commit()
    assert silent(token).status_code == 200
    c = TestClient(app)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": csrf})
    assert "bahn.de: 1 results page with no offers seen" in _page(c)
    assert ">12:04<" in _page(c)
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source="bahn.de", parser_version="1.2.0", captured_at=T0 + timedelta(hours=1),
                      offer_count=2, rejected_count=0))
        s.commit()
    assert "with no offers seen" not in _page(c)


def test_retention_deletes_the_old_rows(sessions):
    now = datetime.now(timezone.utc)
    with sessions() as s:
        s.add_all([SilentPage(source="bahn.de", page_url="/a", seen_at=now - timedelta(days=100), script_version="1"),
                   SilentPage(source="bahn.de", page_url="/b", seen_at=now - timedelta(days=1), script_version="1")])
        s.commit()
        delete_old_captures(s, 90, now)
        s.commit()
        assert [p.page_url for p in s.scalars(select(SilentPage))] == ["/b"]


def test_migration_downgrades_and_upgrades(migrated_url):
    cfg = _alembic(migrated_url)
    command.downgrade(cfg, "0037")
    engine = create_engine(migrated_url)
    try:
        assert "silent_page" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "0038")
        assert "silent_page" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
