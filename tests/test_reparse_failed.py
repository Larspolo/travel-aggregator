"""Reparse all failed captures of one source (#489)."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import ingest, tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Itinerary, Trip
from app.parsers import get_parser

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"
PAGE = "/captures?failed=1"


class RaisingParser:
    version = "0.0.1"

    def parse(self, raw):
        raise ValueError("format changed")


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
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    auth = {"Authorization": f"Bearer {token}"}
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    with monkeypatch.context() as m:
        m.setattr(ingest, "get_parser", lambda source: RaisingParser())
        for source, minute in (("bahn.de", 1), ("bahn.de", 2), ("flixbus.com", 3)):
            r = c.post("/api/ingest", headers=auth, json={
                "trip_id": trip_id, "source": source, "parser_version": "0.0.1",
                "captured_at": f"2026-11-03T19:4{minute}:00Z", "raw": raw})
            assert r.status_code < 300, r.text
    return c, trip_id


def _csrf(c, path):
    groups = re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)
    return next(t for t in groups if t)


def test_reparse_of_one_source(setup, sessions, monkeypatch):
    c, trip_id = setup
    page = c.get(PAGE).text
    assert "failed captures of bahn.de" in page and "failed captures of flixbus.com" in page
    monkeypatch.setattr(ingest, "get_parser",
                        lambda source: get_parser(source) if source == "bahn.de" else RaisingParser())
    r = c.post("/captures/reparse-failed", data={"source": "bahn.de"}, headers={"X-CSRF-Token": _csrf(c, PAGE)})
    assert r.status_code == 200 and "Reparsed 2 captures of bahn.de" in r.text
    assert "2 now parse, 0 still fail" in r.text
    with sessions() as s:
        flix = s.scalars(select(Capture).where(Capture.source == "flixbus.com")).one()
        assert flix.unreadable
    assert "failed captures of bahn.de" not in c.get(PAGE).text
    with sessions() as s:
        assert s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).first() is not None
    assert c.get(f"/trips/{trip_id}").status_code == 200


def test_capture_with_no_raw_is_not_counted(setup, sessions):
    c, trip_id = setup
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source="other.example", captured_at=datetime.now(UTC), unreadable="x"))
        s.commit()
    assert "other.example" not in c.get(PAGE).text.split("<table>")[0]


def test_reparse_failed_needs_login_and_csrf(setup):
    c, _ = setup
    assert c.post("/captures/reparse-failed", data={"source": "bahn.de"}).status_code in (400, 403)
    anon = TestClient(app)
    r = anon.post("/captures/reparse-failed", data={"source": "bahn.de"}, follow_redirects=False)
    assert r.status_code in (302, 303, 307) and "/login" in r.headers["location"]
