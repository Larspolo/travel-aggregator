"""Reparse the good captures of an older parser version per source (#1990)."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, FarePrice, Trip
from app.parsers import get_parser

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"
PAGE = "/captures"


def _csrf(c, path):
    groups = re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)
    return next(t for t in groups if t)


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
    for minute in range(7):
        r = c.post("/api/ingest", headers=auth, json={
            "trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0",
            "captured_at": f"2026-11-03T19:4{minute}:00Z", "raw": raw})
        assert r.status_code < 300, r.text
    with sessions() as s:
        caps = s.scalars(select(Capture).order_by(Capture.id)).all()
        for cap in caps[:3]:
            cap.parsed_with = "1.3.0"
        caps[3].parsed_with = None
        caps[4].parsed_with = "1.3.0"
        caps[4].raw_gz = None  # no raw payload
        caps[5].parsed_with = "1.3.0"
        caps[5].unreadable = "broken"  # failed
        caps[6].parsed_with = "1.4.0"  # current
        s.commit()
    monkeypatch.setattr(type(get_parser("bahn.de")), "version", "1.4.0")
    return c


def test_reparse_old_captures(setup, sessions):
    c = setup
    page = c.get(PAGE).text
    assert "4 captures of an older version" in page
    assert "Reparse with version 1.4.0" in page
    with sessions() as s:
        before = s.scalar(select(func.count(FarePrice.id)))
    r = c.post("/captures/reparse-old", data={"source": "bahn.de"}, headers={"X-CSRF-Token": _csrf(c, PAGE)})
    assert r.status_code == 200
    assert "Reparsed 4 captures of bahn.de with 1.4.0" in r.text
    assert "0 now fail" in r.text
    with sessions() as s:
        assert s.scalar(select(func.count(FarePrice.id))) == before
        versions = [cap.parsed_with for cap in s.scalars(select(Capture).order_by(Capture.id))]
    assert versions[:4] == ["1.4.0"] * 4
    assert versions[4] == "1.3.0" and versions[5] == "1.3.0"
    assert "captures of an older version" not in c.get(PAGE).text


def test_reparse_old_needs_csrf(setup):
    r = setup.post("/captures/reparse-old", data={"source": "bahn.de"})
    assert r.status_code == 403

