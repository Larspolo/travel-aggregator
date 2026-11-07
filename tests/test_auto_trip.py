"""An ingest with `auto_trip` stores the offers into the planning trip that matches them (#719)."""

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.main import app
from app.models import Capture, Itinerary, Trip
from tests.test_ingest_api import BODY


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        zurich = Trip(title="To Zürich", origin_text="Amsterdam", destination_text="Zürich",
                      date_from=date(2026, 12, 20), status="planning")
        lisbon = Trip(title="To Lisbon", origin_text="Amsterdam", destination_text="Lisbon", status="planning")
        s.add_all([zurich, lisbon])
        s.commit()
        ids = zurich.id, lisbon.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, ids


def post(client, auth, trip_id, **change):
    b = copy.deepcopy(BODY)
    b.update(trip_id=trip_id, **change)
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.status_code == 200
    return r.json()


def stored_in(sessions):
    with sessions() as s:
        return s.scalar(select(Itinerary.trip_id)), s.scalar(select(Capture.trip_id))


def test_auto_trip_stores_into_the_matching_planning_trip(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    r = post(client, auth, lisbon, auto_trip=True)
    assert (r["trip_id"], r["trip_title"], r["warning"]) == (zurich, "To Zürich", None)
    assert stored_in(sessions) == (zurich, zurich)


def test_the_selected_trip_wins_when_it_matches(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    with sessions() as s:
        s.add(Trip(title="Wide", origin_text="Amsterdam", destination_text="Zurich", status="planning"))
        s.commit()
    r = post(client, auth, zurich, auto_trip=True)
    assert r["trip_id"] == zurich and stored_in(sessions) == (zurich, zurich)


def test_an_archived_trip_is_never_chosen(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    with sessions() as s:
        s.get(Trip, zurich).status = "archived"
        s.commit()
    r = post(client, auth, lisbon, auto_trip=True)
    assert r["trip_id"] == lisbon and r["warning"] and stored_in(sessions) == (lisbon, lisbon)


def test_no_match_keeps_the_selected_trip_with_the_warning(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    b = copy.deepcopy(BODY["offers"])
    b[0]["legs"][-1]["to_name"] = "Chur"
    r = post(client, auth, lisbon, auto_trip=True, offers=b)
    assert (r["trip_id"], r["trip_title"]) == (lisbon, "To Lisbon") and r["warning"]


def test_without_auto_trip_the_selected_trip_is_used(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    r = post(client, auth, lisbon)
    assert r["trip_id"] == lisbon and r["warning"] and stored_in(sessions) == (lisbon, lisbon)


def test_of_two_matches_the_shortest_date_range_wins(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    with sessions() as s:
        s.add(Trip(title="Winter", origin_text="Amsterdam", destination_text="Zürich", date_from=date(2026, 12, 1),
                   date_to=date(2026, 12, 31), status="planning"))
        s.commit()
    assert post(client, auth, lisbon, auto_trip=True)["trip_id"] == zurich
