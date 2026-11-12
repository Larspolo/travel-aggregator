"""The stops of a leg show as a closed list on the trip page and on the Upcoming page (#2635)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, LegStop, Trip
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=5, minute=0, second=0, microsecond=0) + timedelta(days=10)
STOPS = [
    {"name": "Hilversum", "depart_at": "2026-11-20T06:22:00+01:00", "platform": "3"},
    {"name": "Amersfoort Centraal", "arrive_at": "2026-11-20T06:36:00+01:00", "platform": "1"},
]


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def book_with_stops(sessions, stops):
    with sessions() as s:
        trip_row = Trip(title="Stops trip", origin_text="Amsterdam", destination_text="Berlin", status="planning")
        depart = SOON
        arrive = depart + timedelta(hours=2)
        leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 1", from_name="Amsterdam", to_name="Berlin",
                  depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
        leg.stops = [LegStop(seq=i, name=st["name"], depart_at=depart + timedelta(minutes=5 + 14 * i),
                             depart_offset_min=60, platform=st.get("platform"))
                     for i, st in enumerate(stops)]
        trip_row.itineraries = [Itinerary(fingerprint="stops", depart_at=depart, arrive_at=arrive,
                                          duration_min=120, booked=True, legs=[leg])]
        s.add(trip_row)
        s.commit()


def test_a_leg_with_two_stops_shows_the_list_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["stops"] = STOPS
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "<summary>2 stops</summary>" in page
    assert "06:22 Hilversum, platform 3" in page
    assert "06:36 Amersfoort Centraal, platform 1" in page


def test_a_leg_without_stops_shows_no_stops_element(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [reserved(None, None)])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "leg-stops" not in page


def test_a_stop_name_is_escaped_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["stops"] = [{"name": "<b>x</b>", "depart_at": "2026-11-20T06:22:00+01:00"}]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "&lt;b&gt;x&lt;/b&gt;" in page
    assert "<b>x</b>" not in page


def test_a_booked_journey_shows_the_stops_on_the_upcoming_page(client, sessions):
    book_with_stops(sessions, STOPS)
    page = client.get("/upcoming").text
    assert "<summary>2 stops</summary>" in page
    assert "Hilversum, platform 3" in page
    assert "Amersfoort Centraal, platform 1" in page


def test_a_booked_journey_without_stops_shows_no_stops_element_on_the_upcoming_page(client, sessions):
    book_with_stops(sessions, [])
    page = client.get("/upcoming").text
    assert "leg-stops" not in page
