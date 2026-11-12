"""The notices of a connection show on the trip page and on the Upcoming page (#2625)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def book_with_notices(sessions, notices):
    with sessions() as s:
        trip_row = Trip(title="Notice trip", origin_text="Amsterdam", destination_text="Berlin", status="planning")
        depart = SOON
        arrive = depart + timedelta(hours=2)
        leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 1", from_name="Amsterdam", to_name="Berlin",
                  depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
        trip_row.itineraries = [Itinerary(fingerprint="notice", depart_at=depart, arrive_at=arrive,
                                          duration_min=120, booked=True, legs=[leg], notices=notices)]
        s.add(trip_row)
        s.commit()


def test_a_low_notice_of_leg_0_shows_under_the_leg_without_a_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["notices"] = [{"text": "Track repairs", "level": "low", "leg": 0}]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<div class="leg-notices muted"><span>Track repairs</span> </div>' in page
    assert "badge notice" not in page


def test_a_high_notice_puts_a_badge_on_the_collapsed_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["notices"] = [{"text": "Track repairs", "level": "high", "leg": 0}]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="badge notice" title="Track repairs">notice</span>' in page


def test_a_whole_connection_notice_shows_in_the_expanded_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["notices"] = [{"text": "Bike space limited", "level": "low", "leg": None}]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<div class="notices"><p>Bike space limited</p></div>' in page


def test_an_offer_without_notices_shows_no_notice_element(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [reserved(None, None)])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "leg-notices" not in page
    assert 'class="notices"' not in page
    assert "badge notice" not in page


def test_a_notice_text_is_escaped_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["notices"] = [{"text": "<b>x</b>", "level": "low", "leg": 0}]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "&lt;b&gt;x&lt;/b&gt;" in page
    assert "<b>x</b>" not in page


def test_a_booked_journey_shows_its_notice_on_the_upcoming_page(client, sessions):
    book_with_notices(sessions, [{"text": "Track repairs", "level": "low", "leg": 0}])
    page = client.get("/upcoming").text
    assert '<div class="leg-notices muted"><span>Track repairs</span> </div>' in page


def test_a_booked_journey_without_notices_shows_no_notice_element_on_the_upcoming_page(client, sessions):
    book_with_notices(sessions, None)
    page = client.get("/upcoming").text
    assert "leg-notices" not in page
    assert 'class="notices"' not in page


def test_a_notice_text_is_escaped_on_the_upcoming_page(client, sessions):
    book_with_notices(sessions, [{"text": "<b>x</b>", "level": "low", "leg": None}])
    page = client.get("/upcoming").text
    assert "&lt;b&gt;x&lt;/b&gt;" in page
    assert "<b>x</b>" not in page
