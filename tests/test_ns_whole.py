"""The whole nsinternational.com capture through the API: each fixture, sent as raw, gives its offers on the trip page,
each fare of a connection in the expanded row, and no new rows on a second post (#214, epic #210)."""

import html
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.parsers.ns import NsParser

FIX = Path(__file__).parent / "fixtures" / "nsinternational.com"
FIXTURES = ["search-amsterdam-berlin.json", "search-amsterdam-london.json", "search-rotterdam-paris.json"]


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="nsinternational.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "nsinternational.com", "parser_version": "1.0.0",
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def expected_offers(raw):
    """The offers of the fixture, read from the fixture itself: (price, fare name) per offer that has a price."""
    out = []
    for conn in raw["response"]["data"]["travelOffers"]:
        for o in conn.get("offers") or []:
            price = Decimal(str(o["totalPrice"]["amount"])).quantize(Decimal("0.01"))
            out.append((price, (o.get("name") or "").strip()))
    return out


@pytest.mark.parametrize("name", FIXTURES)
def test_each_offer_is_on_the_trip_page_with_each_fare(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    offers = expected_offers(raw)
    parsed = NsParser().parse(raw)
    assert len(parsed.offers) == len(offers)

    out = post(client, auth, trip_id, raw)
    assert out["created"] + out["updated"] + out["unchanged"] == len(offers)
    assert out["errors"] == parsed.errors

    page = client.get(f"/trips/{trip_id}").text
    for price, fare_name in offers:
        assert f"€{price:.2f}" in page, price
        if fare_name:
            assert html.escape(fare_name) in page, fare_name


@pytest.mark.parametrize("name", FIXTURES)
def test_a_second_post_of_the_same_fixture_is_unchanged(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    first = post(client, auth, trip_id, raw)
    second = post(client, auth, trip_id, raw)
    assert second["created"] == 0 and second["updated"] == 0
    assert second["unchanged"] == first["created"] + first["updated"] + first["unchanged"]
    assert second["errors"] == first["errors"]
