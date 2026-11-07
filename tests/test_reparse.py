"""The "reparse capture" action (#154)."""

import json
from datetime import UTC, datetime
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import ingest, tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Itinerary, Trip
from app.parsers import ParseResult

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"


class BrokenParser:
    source, version = "bahn.de", "0.0.1"

    def parse(self, raw):
        return ParseResult()


@pytest.fixture
def setup(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Köln – München")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, trip_id


def _token(c, path):
    return re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)


def _csrf(c, path):
    return next(t for t in _token(c, path) if t)


def _ingest(c, auth, trip_id, raw):
    r = c.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                                                  "captured_at": "2026-11-03T19:41:00Z", "raw": raw})
    assert r.status_code < 300, r.text


def _count(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == trip_id))


def _capture_id(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Capture.id).where(Capture.trip_id == trip_id))


def test_reparse_after_a_parser_fix_gives_the_offers(setup, sessions, monkeypatch):
    c, auth, trip_id = setup
    with monkeypatch.context() as m:
        m.setattr(ingest, "get_parser", lambda source: BrokenParser())
        _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    assert _count(sessions, trip_id) == 0
    page = f"/trips/{trip_id}/captures"
    cid = _capture_id(sessions, trip_id)
    assert f"/captures/{cid}/reparse" in c.get(page).text
    r = c.post(f"/captures/{cid}/reparse", headers={"X-CSRF-Token": _csrf(c, page)})
    assert r.status_code == 200
    created = _count(sessions, trip_id)
    assert created > 0
    assert f"{created} created" in r.text
    again = c.post(f"/captures/{cid}/reparse", headers={"X-CSRF-Token": _csrf(c, page)})
    assert "0 created" in again.text and _count(sessions, trip_id) == created


def test_capture_with_no_raw_gives_a_clear_message(setup, sessions):
    c, auth, trip_id = setup
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source="bahn.de", captured_at=datetime.now(UTC)))
        s.commit()
    # The button is not shown for a capture without raw data (#451): the token comes from the login page.
    r = c.post(f"/captures/{_capture_id(sessions, trip_id)}/reparse", headers={"X-CSRF-Token": _csrf(c, "/login")})
    assert r.status_code == 200 and "no raw data" in r.text


def test_reparse_needs_the_csrf_token(setup, sessions):
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    r = c.post(f"/captures/{_capture_id(sessions, trip_id)}/reparse")
    assert r.status_code in (400, 403)


def test_trip_page_links_to_the_captures(setup):
    c, _, trip_id = setup
    assert f"/trips/{trip_id}/captures" in c.get(f"/trips/{trip_id}").text
