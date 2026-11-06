"""The whole price history (#243, epic #239): two captures of the same itinerary through the ingest API show as two
points of the chart and two rows of the table, the newest first; the trip page shows the latest price."""

import copy

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_ingest_api import BODY


@pytest.fixture
def trip(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def capture(client, auth, trip_id, price, captured_at):
    """One capture of the same itinerary (ICE 105, Sparpreis) at the given price and time."""
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, captured_at=captured_at)
    offer = copy.deepcopy(BODY["offers"][0])
    offer.update(price_amount=price)
    body["offers"] = [offer]
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def itinerary_id(sessions, trip_id):
    with sessions() as s:
        return s.query(Itinerary).filter_by(trip_id=trip_id).one().id


def test_two_captures_are_two_chart_points_and_two_rows_newest_first(trip, sessions):
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "89.90", "2026-11-03T19:41:00Z")
    capture(client, auth, trip_id, "85.00", "2026-11-04T19:41:00Z")
    it = itinerary_id(sessions, trip_id)

    r = client.get(f"/trips/{trip_id}/itineraries/{it}/history")
    assert r.status_code == 200
    chart_part = r.text[:r.text.index('<table class="history">')]
    table = r.text[r.text.index('<table class="history">'):]

    # the chart: one line of two points
    assert chart_part.count('<circle ') == 2
    assert chart_part.count('<polyline ') == 1
    # the table: two prices, the newest (85.00) first
    assert table.count("<tr><td>") == 2
    assert table.index("EUR 85.00") < table.index("EUR 89.90")


def test_the_trip_page_shows_the_latest_price(trip, sessions):
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "89.90", "2026-11-03T19:41:00Z")
    capture(client, auth, trip_id, "85.00", "2026-11-04T19:41:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert "EUR 85.00" in page
    assert "EUR 89.90" not in page  # the older capture is in the history, not the price of the row
