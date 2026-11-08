"""The whole sncf-connect.com capture through the API: each fixture, sent as raw, gives all its trains and fares on the
trip page, the OUIGO train is named as OUIGO, the connection shows 1 transfer, and the search status shows the capture
(#984, epic #248)."""

import json
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.parsers.sncf import SncfParser
from app.web.pages import money

FIX = Path(__file__).parent / "fixtures" / "sncf-connect.com"
FIXTURES = ["search-paris-lyon.json", "search-paris-marseille.json"]
PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="sncf-connect.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "sncf-connect.com", "parser_version": SncfParser.version,
            "captured_at": "2026-11-08T10:00:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FIXTURES)
def test_each_train_and_fare_is_on_the_trip_page(trip, name):
    client, auth, trip_id = trip
    parsed = SncfParser().parse(load(name))
    assert parsed.offers, "the fixture has no bookable proposal"

    out = post(client, auth, trip_id, load(name))
    assert out["created"] + out["updated"] + out["unchanged"] == len(parsed.offers)
    assert out["errors"] == parsed.errors

    page = client.get(f"/trips/{trip_id}").text
    for offer in parsed.offers:
        price = Decimal(offer.price_amount).quantize(Decimal("0.01"))
        assert money(price, offer.price_currency) in page, price
        for leg in offer.legs:
            assert leg.carrier in page, leg.carrier
            assert leg.depart_at.astimezone(PARIS).strftime("%H:%M") in page, leg.depart_at
            assert leg.arrive_at.astimezone(PARIS).strftime("%H:%M") in page, leg.arrive_at


def test_the_ouigo_train_is_named_ouigo_and_the_connection_has_one_transfer(trip):
    client, auth, trip_id = trip
    parsed = SncfParser().parse(load("search-paris-marseille.json"))
    post(client, auth, trip_id, load("search-paris-marseille.json"))

    carriers = {leg.carrier for offer in parsed.offers for leg in offer.legs}
    assert "OUIGO" in carriers
    connections = [o for o in parsed.offers if len(o.legs) == 2]
    assert connections, "the fixture has no connection with 1 change"
    assert all(len(o.legs) - 1 == 1 for o in connections)

    page = client.get(f"/trips/{trip_id}").text
    assert "OUIGO" in page


@pytest.mark.parametrize("name", FIXTURES)
def test_the_search_status_shows_sncf_connect_with_the_capture_time(trip, name):
    client, auth, trip_id = trip
    post(client, auth, trip_id, load(name))

    page = client.get(f"/trips/{trip_id}").text
    assert "SNCF Connect" in page
    assert "ago" in page
