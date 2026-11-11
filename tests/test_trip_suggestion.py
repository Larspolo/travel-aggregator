"""The trip that an auto_trip capture suggests when no trip matches (#720, #718)."""

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.main import app
from app.models import Trip
from tests.test_ingest_api import BODY


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        lisbon = Trip(title="To Lisbon", origin_text="Amsterdam", destination_text="Lisbon", status="planning")
        zurich = Trip(title="To Zürich", origin_text="Amsterdam", destination_text="Zürich",
                      date_from=date(2026, 12, 20), status="planning")
        s.add_all([lisbon, zurich])
        s.commit()
        ids = lisbon.id, zurich.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, ids


def offers_to_zurich():
    """One offer from Amsterdam Centraal to Zürich HB on 2026-12-20 (the first leg and the last leg name the places)."""
    offer = copy.deepcopy(BODY["offers"][0])
    offer["legs"][0]["from_name"] = "Amsterdam Centraal"
    offer["legs"][-1]["to_name"] = "Zürich HB"
    return [offer]


def post(client, auth, trip_id, **change):
    b = copy.deepcopy(BODY)
    b.update(trip_id=trip_id, **change)
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_no_matching_trip_gives_a_suggestion_that_the_trips_api_accepts(setup, sessions):
    client, auth, (lisbon, zurich) = setup
    with sessions() as s:  # the only trip that would match is archived: no planning trip matches
        s.get(Trip, zurich).status = "archived"
        s.commit()
    r = post(client, auth, lisbon, auto_trip=True, offers=offers_to_zurich())
    suggestion = r["suggestion"]
    assert suggestion == {"title": "Amsterdam Centraal → Zürich HB", "origin_text": "Amsterdam Centraal",
                          "destination_text": "Zürich HB", "date_from": "2026-12-20"}
    assert client.post("/api/trips", json=suggestion, headers=auth).status_code == 201


def test_a_matching_trip_gives_no_suggestion(setup):
    client, auth, (_lisbon, zurich) = setup
    r = post(client, auth, zurich, auto_trip=True, offers=offers_to_zurich())
    assert r["trip_id"] == zurich and r["suggestion"] is None


def test_without_auto_trip_there_is_no_suggestion(setup):
    client, auth, (lisbon, _zurich) = setup
    r = post(client, auth, lisbon, offers=offers_to_zurich())
    assert r["warning"] and r["suggestion"] is None


def test_an_empty_capture_gives_no_suggestion(setup, sessions):
    client, auth, (lisbon, zurich) = setup
    with sessions() as s:
        s.get(Trip, zurich).status = "archived"
        s.commit()
    r = post(client, auth, lisbon, auto_trip=True, offers=[], raw={"journeys": []})
    assert r["suggestion"] is None
