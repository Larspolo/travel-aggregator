"""GET /trips/{id}/itineraries/{id}/history (#240): a table per fare with its captures, the newest first; an
itinerary of another trip gives 404; no login goes to the login page."""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import FarePrice, Itinerary, Trip
from tests.test_trip_page import ingest, offer


@pytest.fixture
def trip(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    yield client, trip_id
    app.dependency_overrides.pop(require_login, None)


def _itinerary_id(sessions, trip_id):
    with sessions() as s:
        return s.query(Itinerary).filter_by(trip_id=trip_id).one().id


def _add_later_price(sessions, itinerary, price):
    """A second capture of the only fare, one day after the first (the ingest time is fixed in the fixtures)."""
    with sessions() as s:
        it = s.get(Itinerary, itinerary)
        fare = it.fares[0]
        first = min(p.captured_at for p in fare.prices)
        fare.prices.append(FarePrice(price=Decimal(price), currency="EUR", captured_at=first + timedelta(days=1)))
        s.commit()


def test_two_captures_show_two_rows_newest_first(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    _add_later_price(sessions, it, "85.00")
    r = client.get(f"/trips/{trip_id}/itineraries/{it}/history")
    assert r.status_code == 200
    assert '<table class="history">' in r.text
    assert "Sparpreis" in r.text
    assert r.text.count("<tr><td>") == 2
    assert r.text.index("EUR 85.00") < r.text.index("EUR 89.90")
    assert "<html" not in r.text  # a fragment, no page


def test_an_itinerary_of_another_trip_gives_404(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    with sessions() as s:
        other = Trip(title="Other")
        s.add(other)
        s.commit()
        other_id = other.id
    assert client.get(f"/trips/{other_id}/itineraries/{it}/history").status_code == 404


def test_no_login_goes_to_the_login_page(sessions):
    app.dependency_overrides.pop(require_login, None)
    client = TestClient(app)
    r = client.get("/trips/1/itineraries/1/history", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"].startswith("/login")
