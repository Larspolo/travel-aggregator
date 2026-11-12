"""The planned platforms of a leg show on the trip page and on the Upcoming page (#2592)."""

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


def book_with_platforms(sessions, from_platform, to_platform):
    with sessions() as s:
        trip_row = Trip(title="Platform trip", origin_text="Amsterdam", destination_text="Berlin", status="planning")
        depart = SOON
        arrive = depart + timedelta(hours=2)
        leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 1", from_name="Amsterdam", to_name="Berlin",
                  depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60,
                  from_platform=from_platform, to_platform=to_platform)
        trip_row.itineraries = [Itinerary(fingerprint="platform", depart_at=depart, arrive_at=arrive,
                                          duration_min=120, booked=True, legs=[leg])]
        s.add(trip_row)
        s.commit()


def test_both_platforms_show_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["from_platform"] = "8b"
    offer["legs"][0]["to_platform"] = "4"
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="leg-platforms muted">planned platform 8b → 4</span>' in page


def test_one_platform_shows_a_question_mark_for_the_other(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["from_platform"] = "8b"
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "planned platform 8b → ?" in page


def test_a_leg_without_platforms_shows_no_platform_text(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "leg-platforms" not in page
    assert "planned platform" not in page


def test_both_platforms_show_on_the_upcoming_page(client, sessions):
    book_with_platforms(sessions, "8b", "4")
    page = client.get("/upcoming").text
    assert "planned platform 8b → 4" in page


def test_one_platform_shows_a_question_mark_on_the_upcoming_page(client, sessions):
    book_with_platforms(sessions, "8b", None)
    page = client.get("/upcoming").text
    assert "planned platform 8b → ?" in page


def test_no_platforms_show_no_text_on_the_upcoming_page(client, sessions):
    book_with_platforms(sessions, None, None)
    page = client.get("/upcoming").text
    assert "leg-platforms" not in page
