"""The whole eurostar.com capture through the API: each fixture, sent as raw, gives its journeys and fares on the trip
page with the local times of London and the continent (#1020, #980)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.parsers.eurostar import EurostarParser
from app.web.pages import money

FIX = Path(__file__).parent / "fixtures" / "eurostar.com"
AMS_LON = FIX / "search-amsterdam-london.json"
BRU_PAR = FIX / "search-brussels-paris.json"


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="eurostar.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "eurostar.com", "parser_version": "1.0.0",
            "captured_at": "2026-11-08T09:00:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_amsterdam_london_shows_train_9115_with_its_three_fares(trip):
    client, auth, trip_id = trip
    out = post(client, auth, trip_id, load(AMS_LON))
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    assert "9115" in page
    # the local times: Amsterdam (CET) for the departure, London (GMT) for the arrival
    assert "06:40" in page
    assert "09:57" in page
    for price in ("56.50", "82.50", "319.00"):
        assert money(Decimal(price), "GBP") in page, price


def test_brussels_paris_shows_both_0813_trains_and_no_premier_for_1813(trip):
    client, auth, trip_id = trip
    out = post(client, auth, trip_id, load(BRU_PAR))
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    assert "9410" in page
    assert "9310" in page
    assert "08:13" in page
    assert "18:13" in page
    # the 18:13 train (9370) has its Standard and Plus fares, and no Premier fare (sold out in the capture)
    assert money(Decimal("70.50"), "GBP") in page
    assert money(Decimal("83.50"), "GBP") in page

    parsed = EurostarParser().parse(load(BRU_PAR))
    premier_1813 = [o for o in parsed.offers
                    if o.legs[0].service_no == "9370" and o.travel_class == "first"]
    assert premier_1813 == []
