"""GET /trips/{id} (#7): the offers of a trip with their prices, cheapest first; captured text is escaped; the page
needs the owner login."""

import copy

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_ingest_api import BODY


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def ingest(client, auth, trip_id, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=offers)
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def offer(price, service_no="ICE 105", carrier="DB", fare="Sparpreis"):
    o = copy.deepcopy(BODY["offers"][0])
    o.update(price_amount=price, fare_name=fare)
    o["legs"][0].update(service_no=service_no, carrier=carrier)
    return o


def test_the_page_shows_each_offer_with_its_price_cheapest_first(trip):
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("119.90", "ICE 123"), offer("89.90", "ICE 105")])
    r = client.get(f"/trips/{trip_id}")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    page = r.text
    assert "€89.90" in page and "€119.90" in page and page.index("€89.90") < page.index("€119.90")
    assert "Amsterdam Centraal → Zürich HB" in page and "Sun 20 Dec 07:34 → 15:26" in page
    assert "Deutsche Bahn ICE 105, SBB IC 61" in page and "Sparpreis" in page and "1 transfer" in page


def test_captured_text_is_escaped(trip):
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("10.00", carrier="<script>alert(1)</script>")])
    page = client.get(f"/trips/{trip_id}").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_an_empty_trip_and_an_unknown_trip(trip):
    client, _, trip_id = trip
    assert "No offers yet" in client.get(f"/trips/{trip_id}").text
    assert client.get(f"/trips/{trip_id + 1}").status_code == 404


def test_the_page_needs_the_login(trip):
    client, _, trip_id = trip
    app.dependency_overrides.pop(require_login)
    r = client.get(f"/trips/{trip_id}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=%2F")  # the target of #2103
