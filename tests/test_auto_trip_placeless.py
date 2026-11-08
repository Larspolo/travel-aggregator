"""`auto_trip` never moves a capture to a planning trip with no places (found in the owner check of #752 on
2026-11-08). A trip with no origin and no destination matches each offer for the warning of #555, but it is no
target for another search: on the preview, each `scripts/preview_check.sh` run makes such a trip ("agent check"),
and a bahn.de search Amsterdam → Wien went there in place of "No trip matches: + new trip" (#720)."""

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.main import app
from app.models import Itinerary, Trip
from tests.test_ingest_api import BODY


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        lisbon = Trip(title="To Lisbon", origin_text="Amsterdam", destination_text="Lisbon",
                      date_from=date(2026, 12, 20), status="planning")
        placeless = Trip(title="agent check", status="planning")
        s.add_all([lisbon, placeless])
        s.commit()
        ids = lisbon.id, placeless.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, ids


def post(client, auth, trip_id, offers=None, **change):
    b = copy.deepcopy(BODY)
    b.update(trip_id=trip_id, auto_trip=True, **change)
    if offers is not None:
        b["offers"] = offers
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.status_code == 200
    return r.json()


def to_chur():
    offers = copy.deepcopy(BODY["offers"])
    for o in offers:
        o["legs"][-1]["to_name"] = "Chur"
    return offers


def test_no_match_gives_the_suggestion_and_not_the_trip_with_no_places(setup, sessions):
    client, auth, (lisbon, placeless) = setup
    r = post(client, auth, lisbon, offers=to_chur())
    assert r["trip_id"] == lisbon and r["warning"]
    assert r["suggestion"] is not None
    with sessions() as s:
        assert s.scalars(select(Itinerary).where(Itinerary.trip_id == placeless)).first() is None


def test_a_trip_with_no_places_that_the_owner_selected_keeps_the_capture(setup, sessions):
    client, auth, (lisbon, placeless) = setup
    r = post(client, auth, placeless, offers=to_chur())
    assert r["trip_id"] == placeless and r["warning"] is None and r["suggestion"] is None
