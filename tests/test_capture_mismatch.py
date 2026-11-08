"""The trip warning of a capture is stored (#556) and shown on the captures pages; a reparse updates it."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"
WARNING = "These offers do not match the trip"


def _token(c, path):
    return re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)


def _csrf(c, path):
    return next(t for t in _token(c, path) if t)


def _setup(sessions, monkeypatch, destination):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Köln – München", origin_text="Köln", destination_text=destination)
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, trip_id


def _ingest_raw(c, auth, trip_id):
    raw = json.loads(FIX.read_text())
    r = c.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                                                  "captured_at": "2026-11-03T19:41:00Z", "raw": raw})
    assert r.status_code < 300, r.text
    return r.json()


def test_a_capture_into_a_wrong_trip_shows_the_warning_on_both_pages(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="Lisboa")
    assert _ingest_raw(c, auth, trip_id)["warning"] is not None
    assert WARNING in c.get(f"/trips/{trip_id}/captures").text
    assert WARNING in c.get("/captures").text


def test_a_capture_into_the_correct_trip_shows_no_warning(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    assert _ingest_raw(c, auth, trip_id)["warning"] is None
    assert WARNING not in c.get(f"/trips/{trip_id}/captures").text
    assert WARNING not in c.get("/captures").text


def test_a_reparse_after_the_trip_got_the_correct_places_removes_the_warning(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="Lisboa")
    _ingest_raw(c, auth, trip_id)
    with sessions() as s:
        capture_id = s.scalar(select(Capture.id).where(Capture.trip_id == trip_id))
        assert s.get(Capture, capture_id).mismatch == "places"
        trip = s.get(Trip, trip_id)
        trip.destination_text = "München"
        s.commit()
    assert WARNING in c.get(f"/trips/{trip_id}/captures").text
    r = c.post(f"/captures/{capture_id}/reparse", headers={"X-CSRF-Token": _csrf(c, "/captures")})
    assert r.status_code == 200
    with sessions() as s:
        assert s.get(Capture, capture_id).mismatch is None
    assert WARNING not in c.get(f"/trips/{trip_id}/captures").text
