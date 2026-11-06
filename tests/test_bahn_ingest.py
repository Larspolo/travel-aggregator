"""POST /api/ingest with a bahn.de raw capture (#153): the parser of the source makes the offers, one bad connection is
an entry of errors[] and the other offers are stored, and each failure is logged with the capture id."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.main import app
from app.models import Capture, Itinerary, Trip

FIX = Path(__file__).parent / "fixtures" / "bahn.de"


def raw_fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Köln – München")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id


def body(trip_id, raw, **change):
    b = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0",
         "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    b.update(change)
    return b


def test_raw_capture_stores_the_offers_of_the_parser(setup, sessions):
    client, auth, trip_id = setup
    r = client.post("/api/ingest", json=body(trip_id, raw_fixture("fahrplan-koeln-muenchen-bahncard25.json")),
                    headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 3
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == trip_id)) == 3


def test_bad_connection_is_an_error_and_the_others_are_stored(setup, sessions, caplog):
    client, auth, trip_id = setup
    caplog.set_level(logging.WARNING, logger="app.ingest")
    r = client.post("/api/ingest", json=body(trip_id, raw_fixture("fahrplan-koeln-muenchen.json")), headers=auth)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 2
    assert out["rejected"] == 1
    assert out["errors"] == [{"index": 1, "reason": "no price (angebotsPreis)"}]
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == trip_id)) == 2


def test_each_failure_is_logged_with_the_capture_id(setup, sessions, caplog):
    client, auth, trip_id = setup
    caplog.set_level(logging.WARNING, logger="app.ingest")
    r = client.post("/api/ingest", json=body(trip_id, raw_fixture("fahrplan-koeln-muenchen.json")), headers=auth)
    assert r.status_code == 200, r.text
    with sessions() as s:
        capture_id = s.scalar(select(Capture.id).order_by(Capture.id.desc()))
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "app.ingest"]
    assert len(lines) == 1
    assert f"capture {capture_id}:" in lines[0]
    assert "no price (angebotsPreis)" in lines[0]


def test_unreadable_raw_keeps_the_capture_and_is_logged_with_its_id(setup, sessions, caplog):
    client, auth, trip_id = setup
    caplog.set_level(logging.WARNING, logger="app.ingest")
    r = client.post("/api/ingest", json=body(trip_id, {"nothing": True}), headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    with sessions() as s:
        capture_id = s.scalar(select(Capture.id).order_by(Capture.id.desc()))
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "app.ingest"]
    assert lines == [f"capture {capture_id}: bahn.de raw payload not read: the bahn.de payload has no verbindungen list"]
