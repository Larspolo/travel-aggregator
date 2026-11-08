"""The whole bahn.de capture through the API: each fixture, sent as raw, gives its priced connections on the trip page,
one errors[] entry per connection with no price, and no new rows on a second post (#153, epic #151)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip

FIX = Path(__file__).parent / "fixtures" / "bahn.de"
FIXTURES = ["fahrplan-koeln-muenchen.json", "fahrplan-amsterdam-zuerich.json",
            "fahrplan-amsterdam-bern-night.json", "fahrplan-koeln-muenchen-bahncard25.json"]


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="bahn.de")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0",
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def priced_prices(raw):
    """The prices of the connections that have a price: the expected rows, read from the fixture itself."""
    out = []
    for conn in raw["response"]["verbindungen"]:
        price = conn.get("angebotsPreis")
        if price and price.get("betrag") is not None:
            out.append(Decimal(str(price["betrag"])).quantize(Decimal("0.01")))
    return out


@pytest.mark.parametrize("name", FIXTURES)
def test_each_priced_connection_is_on_the_trip_page(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    prices = priced_prices(raw)
    unpriced = len(raw["response"]["verbindungen"]) - len(prices)

    out = post(client, auth, trip_id, raw)
    assert out["created"] == len(prices)
    assert len(out["errors"]) == unpriced
    assert [e["index"] for e in out["errors"]] == [
        i for i, c in enumerate(raw["response"]["verbindungen"]) if not (c.get("angebotsPreis") or {}).get("betrag")]

    page = client.get(f"/trips/{trip_id}").text
    for price in prices:
        assert f"€{price:.2f}" in page, price


@pytest.mark.parametrize("name", FIXTURES)
def test_a_second_post_of_the_same_fixture_is_unchanged(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    first = post(client, auth, trip_id, raw)
    second = post(client, auth, trip_id, raw)
    assert second["created"] == 0 and second["updated"] == 0
    assert second["unchanged"] == first["created"]
    assert second["errors"] == first["errors"]
