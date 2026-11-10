"""POST /trips/{id}/itineraries/hide-filtered (#1898): the "Hide all" button of the filter line hides each offer that
a filter of the page hides. Without a filter the line and the button do not show, and the POST hides nothing;
a POST without the CSRF token gives 403."""

import re

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer


@pytest.fixture
def trip(sessions):
    """A client with the owner login and a trip with five offers: two by DB, three by FlixTrain."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [
        offer("119.90", "ICE 123", carrier="DB"), offer("89.90", "ICE 105", carrier="DB"),
        offer("79.90", "FLX 1", carrier="FlixTrain"), offer("99.90", "FLX 2", carrier="FlixTrain"),
        offer("109.90", "FLX 3", carrier="FlixTrain"),
    ])
    yield client, trip_id
    app.dependency_overrides.pop(require_login, None)


def csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def hidden_carriers(sessions, trip_id):
    with sessions() as s:
        rows = s.query(Itinerary).filter(Itinerary.trip_id == trip_id).all()
        return sorted(leg.carrier for it in rows if it.hidden for leg in it.legs[:1])


def hide_url(trip_id, query=""):
    return f"/trips/{trip_id}/itineraries/hide-filtered?{query}"


def test_hide_all_hides_exactly_the_offers_that_the_filter_hides(trip, sessions):
    client, trip_id = trip
    token = csrf(client, trip_id)
    page = client.get(f"/trips/{trip_id}", params={"exclude_carrier": "DB"}).text
    assert "Hide all 2" in page
    r = client.post(hide_url(trip_id, "exclude_carrier=DB"), data={"csrf_token": token},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert hidden_carriers(sessions, trip_id) == ["DB", "DB"]


def test_without_a_filter_the_button_is_absent_and_the_post_hides_nothing(trip, sessions):
    client, trip_id = trip
    token = csrf(client, trip_id)
    assert "Hide all" not in client.get(f"/trips/{trip_id}").text
    client.post(hide_url(trip_id), data={"csrf_token": token}, follow_redirects=False)
    assert hidden_carriers(sessions, trip_id) == []


def test_a_post_without_the_csrf_token_gets_403_and_changes_nothing(trip, sessions):
    client, trip_id = trip
    csrf(client, trip_id)  # the session has a token now; the form sends none
    r = client.post(hide_url(trip_id, "exclude_carrier=DB"), follow_redirects=False)
    assert r.status_code == 403
    assert hidden_carriers(sessions, trip_id) == []
