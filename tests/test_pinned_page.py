"""The Pinned page lists the pinned, not hidden offers of the trips in planning, in the order of departure (#1299)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(s, title, depart, status="planning", pinned=True, hidden=False, service="IC 1"):
    trip = Trip(title=title, origin_text="A", destination_text="B", status=status)
    arrive = depart + timedelta(hours=2)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no=service, from_name="Amsterdam", to_name="Berlin",
              depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    it = Itinerary(fingerprint=title, depart_at=depart, arrive_at=arrive, duration_min=120,
                   pinned=pinned, hidden=hidden, legs=[leg])
    it.fares = [Fare(source="bahn", latest_price=40, currency="EUR", latest_captured_at=depart)]
    trip.itineraries = [it]
    s.add(trip)
    s.commit()
    return trip.id, it.id


def test_pinned_offers_of_planning_trips_in_departure_order(client, sessions):
    with sessions() as s:
        add(s, "Later trip", SOON + timedelta(days=3), service="ICE 9")
        add(s, "Earlier trip", SOON)
        add(s, "Archived trip", SOON, status="archived")
    html = client.get("/pinned").text
    assert html.index("Earlier trip") < html.index("Later trip")
    assert "Archived trip" not in html
    assert "ICE 9" in html and "Amsterdam → Berlin" in html


def test_hidden_pin_is_not_listed_and_empty_page_says_so(client, sessions):
    with sessions() as s:
        add(s, "Hidden pin", SOON, hidden=True)
    html = client.get("/pinned").text
    assert "Hidden pin" not in html
    assert "No pinned offers" in html


def test_each_row_links_to_its_trip_page_row(client, sessions):
    with sessions() as s:
        trip_id, it_id = add(s, "Linked trip", SOON)
    html = client.get("/pinned").text
    assert f'href="/trips/{trip_id}#it-{it_id}"' in html


def test_no_login_goes_to_login_page(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    response = c.get("/pinned", follow_redirects=False)
    assert response.status_code in (302, 303, 307) and "/login" in response.headers["location"]
