"""The travel class of each fare (#690): the bahn.de and NS parsers set it, and the ingest stores it."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.main import app
from app.models import Fare, Trip
from app.parsers.bahn import BahnParser
from app.parsers.ns import NsParser
from tests.test_ingest_api import BODY

FIX = Path(__file__).parent / "fixtures"


def load(path):
    return json.loads((FIX / path).read_text(encoding="utf-8"))


def test_bahn_gives_first_and_standard():
    # the fahrplan fixture of the ticket has only the 2nd-class angebotsPreis: the recon payload has both classes
    offers = BahnParser().parse(load("bahn.de/recon-169.json")).offers
    classes = {o.travel_class for o in offers}
    assert {"first", "standard"} <= classes
    for o in offers:
        assert o.travel_class == ("first" if "1st class" in (o.fare_name or "") else "standard")


def test_ns_gives_the_class_of_each_offer():
    offers = NsParser().parse(load("nsinternational.com/search-amsterdam-berlin-pair.json")).offers
    assert offers
    for o in offers:
        if o.fare_name.startswith("Comfort Class"):
            assert o.travel_class == "first"
        elif o.fare_name.startswith("Second Class"):
            assert o.travel_class == "standard"
    assert {o.travel_class for o in offers} == {"first", "standard"}


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id


def body(trip_id, travel_class):
    b = copy.deepcopy(BODY)
    b["trip_id"] = trip_id
    b["offers"][0]["travel_class"] = travel_class
    return b


def test_ingest_stores_the_class(setup, sessions):
    client, auth, trip_id = setup
    r = client.post("/api/ingest", json=body(trip_id, "first"), headers=auth)
    assert r.status_code == 200, r.text
    with sessions() as s:
        assert s.scalars(select(Fare.travel_class)).all() == ["first"]


def test_unknown_class_rejects_the_offer(setup):
    # a bad offer is rejected with its index, fail soft (#54); a body with only bad offers stores nothing
    client, auth, trip_id = setup
    r = client.post("/api/ingest", json=body(trip_id, "business"), headers=auth)
    data = r.json()
    assert data["rejected"] == 1 and "travel_class" in data["errors"][0]["reason"]
