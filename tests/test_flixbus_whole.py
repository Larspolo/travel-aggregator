"""The whole flixbus.com capture through the API: each fixture, sent as raw, gives its offers on the trip page with the
bus mode icon and the price, and no new rows on a second post (#252, epic #248)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.parsers.flixbus import FlixbusParser

FIX = Path(__file__).parent / "fixtures" / "flixbus.com"
FIXTURES = ["search-amsterdam-berlin.json", "search-amsterdam-paris.json", "search-utrecht-berlin.json"]


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="flixbus.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "flixbus.com", "parser_version": "1.0.0",
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("name", FIXTURES)
def test_each_offer_is_on_the_trip_page_with_bus_icon_and_price(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    parsed = FlixbusParser().parse(raw)
    assert parsed.offers, "the fixture has no available connection"

    out = post(client, auth, trip_id, raw)
    assert out["created"] + out["updated"] + out["unchanged"] == len(parsed.offers)
    assert out["errors"] == parsed.errors

    page = client.get(f"/trips/{trip_id}").text
    assert "icons.svg#bus" in page
    for offer in parsed.offers:
        price = Decimal(offer.price_amount).quantize(Decimal("0.01"))
        assert f"{offer.price_currency} {price:.2f}" in page, price


@pytest.mark.parametrize("name", FIXTURES)
def test_a_second_post_of_the_same_fixture_is_unchanged(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    first = post(client, auth, trip_id, raw)
    second = post(client, auth, trip_id, raw)
    assert second["created"] == 0 and second["updated"] == 0
    assert second["unchanged"] == first["created"] + first["updated"] + first["unchanged"]
    assert second["errors"] == first["errors"]
