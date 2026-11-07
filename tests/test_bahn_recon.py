"""The bahn.de recon response (#445): one fare per fare class, and the fares go to the offer of the fahrplan response."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.ingest import fingerprint
from app.main import app
from app.models import Fare, Itinerary, Trip
from app.parsers.bahn import BahnParser

FIX = Path(__file__).parent / "fixtures" / "bahn.de"
RECON = json.loads((FIX / "recon-169.json").read_text(encoding="utf-8"))
FARES = {
    "Super Sparpreis, 2nd class": "56.99", "Super Sparpreis, 1st class": "70.99",
    "Sparpreis, 2nd class": "65.99", "Sparpreis, 1st class": "81.99",
    "Flexpreis, 2nd class": "167.30", "Flexpreis, 1st class": "309.50",
}


def fahrplan():
    """The fahrplan response of the same connection: no reiseAngebote, only angebotsPreis."""
    raw = copy.deepcopy(RECON)
    raw["url"] = "https://www.bahn.de/web/api/angebote/fahrplan"
    raw["response"]["verbindungen"][0]["reiseAngebote"] = []
    return raw


def test_recon_gives_one_fare_per_class():
    r = BahnParser().parse(RECON)
    assert r.errors == []
    assert {o.fare_name: o.price_amount for o in r.offers} == {k: Decimal(v) for k, v in FARES.items()}
    assert all(isinstance(o.price_amount, Decimal) for o in r.offers)
    assert len({fingerprint(o.legs) for o in r.offers}) == 1


def test_fahrplan_keeps_its_one_price():
    offers = BahnParser().parse(fahrplan()).offers
    assert [(o.fare_name, o.price_amount) for o in offers] == [("2nd class", Decimal("56.99"))]
    assert fingerprint(offers[0].legs) == fingerprint(BahnParser().parse(RECON).offers[0].legs)


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Köln – München")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id


def test_fahrplan_then_recon_is_one_offer_with_all_fares(setup, sessions):
    client, auth, trip_id = setup
    for i, raw in enumerate([fahrplan(), RECON]):
        r = client.post("/api/ingest", headers=auth, json={
            "trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0",
            "captured_at": f"2026-11-03T19:4{i}:00Z", "raw": raw})
        assert r.status_code == 200, r.text
    with sessions() as s:
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == trip_id)).all()
        assert len(ids) == 1
        assert s.scalar(select(func.count()).select_from(Fare).where(Fare.itinerary_id == ids[0])) == len(FARES) + 1
