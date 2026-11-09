"""The other places of a trip match the offers of a capture (#1423): an offer to Basel matches a trip Amsterdam →
Zürich with Basel as the other destination."""

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.main import app
from app.models import Capture, Itinerary, Trip
from app.schemas import OfferIn
from app.tripmatch import best_trip, mismatch
from tests.test_ingest_api import BODY


def offer(to_name: str) -> OfferIn:
    o = copy.deepcopy(BODY["offers"][0])
    o["legs"] = [o["legs"][0]]
    o["legs"][0]["to_name"] = to_name
    return OfferIn.model_validate(o)


def zurich_trip(**kwargs) -> Trip:
    return Trip(title="To Zürich", origin_text="Amsterdam", destination_text="Zürich",
                date_from=date(2026, 12, 20), status="planning", **kwargs)


def test_an_other_destination_matches_the_trip():
    trip = zurich_trip(destination_alt_text="Basel")
    assert mismatch(trip, [offer("Basel SBB")]) is None


def test_a_place_that_is_no_alternative_does_not_match():
    trip = zurich_trip(destination_alt_text="Basel")
    assert mismatch(trip, [offer("Bern")]) == "places"


def test_the_main_destination_still_matches_with_alternatives():
    trip = zurich_trip(destination_alt_text="Basel")
    assert mismatch(trip, [offer("Zürich HB")]) is None


def test_an_other_origin_matches_the_trip():
    trip = Trip(title="To Zürich", origin_text="Amsterdam", destination_text="Zürich", origin_alt_text="Utrecht",
                date_from=date(2026, 12, 20), status="planning")
    o = copy.deepcopy(BODY["offers"][0])
    o["legs"][0]["from_name"] = "Utrecht Centraal"
    assert mismatch(trip, [OfferIn.model_validate(o)]) is None


def test_a_trip_with_only_an_alternative_place_is_chosen_for_it():
    selected = Trip(id=1, title="Lisbon", origin_text="Amsterdam", destination_text="Lisbon", status="planning",
                    date_from=date(2026, 12, 20))
    basel = Trip(id=2, title="Basel", origin_text="Amsterdam", destination_text="Zürich",
                 destination_alt_text="Basel", status="planning", date_from=date(2026, 12, 20))
    assert best_trip([selected, basel], [offer("Basel SBB")], selected) is basel


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        zurich = Trip(title="To Zürich", origin_text="Amsterdam", destination_text="Zürich",
                      destination_alt_text="Basel", date_from=date(2026, 12, 20), status="planning")
        lisbon = Trip(title="To Lisbon", origin_text="Amsterdam", destination_text="Lisbon", status="planning")
        s.add_all([zurich, lisbon])
        s.commit()
        ids = zurich.id, lisbon.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, ids


def test_an_auto_trip_capture_to_the_alternative_goes_to_that_trip(setup, sessions):
    client, auth, (zurich, lisbon) = setup
    b = copy.deepcopy(BODY)
    b.update(trip_id=lisbon, auto_trip=True)
    b["offers"][0]["legs"] = [b["offers"][0]["legs"][0]]
    b["offers"][0]["legs"][0]["to_name"] = "Basel SBB"
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert (body["trip_id"], body["warning"]) == (zurich, None)
    with sessions() as s:
        assert s.scalar(select(Itinerary.trip_id)) == zurich
        assert s.scalar(select(Capture.trip_id)) == zurich
