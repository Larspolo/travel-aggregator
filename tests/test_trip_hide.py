"""POST /trips/{id}/itineraries/{id}/hide (#200): the owner hides an offer; the trip page leaves it out unless
"show hidden" is on; a hidden offer gets no highlight; "Unhide" shows it again."""

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
    """A client with the owner login and a trip with two offers: 89.90 (ICE 105) and 119.90 (ICE 123)."""
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


def itinerary_at(sessions, trip_id, price):
    with sessions() as s:
        rows = s.query(Itinerary).filter_by(trip_id=trip_id).all()
        return next(it.id for it in rows if min(f.latest_price for f in it.fares) == Decimal(price))


def hide_url(trip_id, itinerary):
    return f"/trips/{trip_id}/itineraries/{itinerary}/hide"


def hide(client, trip_id, itinerary):
    token = csrf(client, trip_id)
    return client.post(hide_url(trip_id, itinerary), data={"csrf_token": token}, follow_redirects=False)


def test_a_hidden_offer_is_left_out_until_show_hidden_is_on(trip, sessions):
    client, trip_id = trip
    cheap = itinerary_at(sessions, trip_id, "89.90")
    r = hide(client, trip_id, cheap)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    page = client.get(f"/trips/{trip_id}").text
    assert "€89.90" not in page and "€119.90" in page
    shown = client.get(f"/trips/{trip_id}?show_hidden=true").text
    assert "€89.90" in shown and "€119.90" in shown
    assert '<span class="muted">hidden</span>' in shown


def test_a_hidden_offer_gets_no_highlight_even_when_it_is_the_cheapest(trip, sessions):
    client, trip_id = trip
    cheap = itinerary_at(sessions, trip_id, "89.90")
    hide(client, trip_id, cheap)
    page = client.get(f"/trips/{trip_id}?show_hidden=true").text
    page = page[page.index('id="table"'):]  # the table only: the timeline above it also has the prices (#815)
    # the rows come cheapest first: the badge of the other row sits between the two prices
    assert "cheapest" in page
    assert page.index("€89.90") < page.index("cheapest") < page.index("€119.90")


def test_unhide_shows_the_offer_again(trip, sessions):
    client, trip_id = trip
    cheap = itinerary_at(sessions, trip_id, "89.90")
    hide(client, trip_id, cheap)
    hide(client, trip_id, cheap)
    page = client.get(f"/trips/{trip_id}").text
    assert "€89.90" in page and "€119.90" in page
    assert '<span class="muted">hidden</span>' not in page


def test_an_itinerary_of_another_trip_gives_404(trip, sessions):
    client, trip_id = trip
    cheap = itinerary_at(sessions, trip_id, "89.90")
    with sessions() as s:
        other = Trip(title="Other")
        s.add(other)
        s.commit()
        other_id = other.id
    token = csrf(client, trip_id)  # the other trip has no offers, so its page has no form token
    r = client.post(hide_url(other_id, cheap), data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 404
    with sessions() as s:
        assert s.get(Itinerary, cheap).hidden is False
