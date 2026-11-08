"""The Upcoming page lists the booked itineraries of all trips in the order of departure (#862)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(s, title, depart, booked=True, service="IC 1"):
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
    arrive = depart + timedelta(hours=2)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no=service, from_name="Amsterdam", to_name="Berlin",
              depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    trip.itineraries = [Itinerary(fingerprint=title, depart_at=depart, arrive_at=arrive, duration_min=120,
                                  booked=booked, legs=[leg])]
    s.add(trip)
    s.commit()
    return trip.id, trip.itineraries[0].id


def test_booked_itineraries_show_in_departure_order(client, sessions):
    with sessions() as s:
        late = add(s, "Later trip", SOON + timedelta(days=3), service="ICE 9")
        early = add(s, "Earlier trip", SOON)
        add(s, "Not booked trip", SOON, booked=False)
        add(s, "Past trip", datetime.now(timezone.utc) - timedelta(days=2))
    html = client.get("/upcoming").text
    assert html.index("Earlier trip") < html.index("Later trip")
    assert "Not booked trip" not in html and "Past trip" not in html
    assert "08:12" in html and "ICE 9" in html and "Amsterdam → Berlin" in html
    for trip_id, it_id in (early, late):
        assert f'href="/trips/{trip_id}/itineraries/{it_id}/calendar.ics" download' in html


def test_no_booked_itinerary_shows_the_empty_text(client):
    assert "No booked journeys. Mark an offer as booked on its trip page." in client.get("/upcoming").text


def test_no_login_goes_to_the_login_page(sessions):
    r = TestClient(app).get("/upcoming", follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers["location"].endswith("/login")
