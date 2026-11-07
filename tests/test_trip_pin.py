"""POST /trips/{id}/itineraries/{id}/pin (#199): the owner pins an offer to the top of the trip page and unpins it;
the form needs the CSRF token; an offer of another trip gives 404."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and a trip with two offers: 89.90 (ICE 105) and 119.90 (ICE 123)."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [offer("119.90", "ICE 123"), offer("89.90", "ICE 105")])
    yield client, trip_id
    app.dependency_overrides.pop(require_login, None)


def csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def pin_url(trip_id, itinerary):
    return f"/trips/{trip_id}/itineraries/{itinerary}/pin"


def test_a_post_toggles_the_pin_and_redirects_to_the_trip(trip, sessions):
    client, trip_id = trip
    cheap = _cheap_id(sessions, trip_id)
    token = csrf(client, trip_id)
    r = client.post(pin_url(trip_id, cheap), data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert _pinned(sessions, cheap) is True
    client.post(pin_url(trip_id, cheap), data={"csrf_token": token}, follow_redirects=False)
    assert _pinned(sessions, cheap) is False


def test_a_post_without_the_csrf_token_gets_403_and_changes_nothing(trip, sessions):
    client, trip_id = trip
    cheap = _cheap_id(sessions, trip_id)
    csrf(client, trip_id)  # the session has a token now; the form sends none
    r = client.post(pin_url(trip_id, cheap), follow_redirects=False)
    assert r.status_code == 403
    assert _pinned(sessions, cheap) is False


def test_an_itinerary_of_another_trip_gives_404(trip, sessions):
    client, trip_id = trip
    cheap = _cheap_id(sessions, trip_id)
    with sessions() as s:
        other = Trip(title="Other")
        s.add(other)
        s.commit()
        other_id = other.id
    token = csrf(client, trip_id)
    r = client.post(pin_url(other_id, cheap), data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 404
    assert _pinned(sessions, cheap) is False


def test_a_pinned_offer_is_the_first_row_and_unpinning_restores_the_order(trip, sessions):
    client, trip_id = trip
    expensive = _expensive_id(sessions, trip_id)
    token = csrf(client, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("€89.90") < page.index("€119.90")

    client.post(pin_url(trip_id, expensive), data={"csrf_token": token}, follow_redirects=False)
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("€119.90") < page.index("€89.90")
    assert "pinned" in page

    client.post(pin_url(trip_id, expensive), data={"csrf_token": token}, follow_redirects=False)
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("€89.90") < page.index("€119.90")
    assert "pinned" not in page


def _pinned(sessions, itinerary):
    with sessions() as s:
        return s.get(Itinerary, itinerary).pinned


def _itinerary_at(sessions, trip_id, price):
    with sessions() as s:
        rows = s.query(Itinerary).filter_by(trip_id=trip_id).all()
        return next(it.id for it in rows if min(f.latest_price for f in it.fares) == Decimal(price))


def _cheap_id(sessions, trip_id):
    return _itinerary_at(sessions, trip_id, "89.90")


def _expensive_id(sessions, trip_id):
    return _itinerary_at(sessions, trip_id, "119.90")


@pytest.mark.parametrize("query", ["sort=cost", "sort=price", "dir=desc", "sort=price&dir=desc"])
def test_a_pinned_offer_stays_first_in_every_sort_order(trip, sessions, query):
    client, trip_id = trip
    expensive = _expensive_id(sessions, trip_id)
    token = csrf(client, trip_id)
    client.post(pin_url(trip_id, expensive), data={"csrf_token": token}, follow_redirects=False)
    page = client.get(f"/trips/{trip_id}?{query}").text
    assert page.index("€119.90") < page.index("€89.90")
