"""The booking code shows on the Upcoming page and stays off the shared pages (#1717)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash, token_limiter
from app.calendar_feed import new_feed_token
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

PASSWORD = "pw"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
CODE = "K7Q2XP"


@pytest.fixture(autouse=True)
def _limiter():
    token_limiter.reset()
    yield
    token_limiter.reset()


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def add(sessions, code=None, booked=True, title="Trip T"):
    """A booked journey three days ahead (or not booked); returns (trip id, itinerary id)."""
    with sessions() as s:
        trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
        trip.itineraries = [Itinerary(fingerprint=f"f-{title}-{code}", depart_at=NOW + timedelta(days=3),
                                      arrive_at=NOW + timedelta(days=3, hours=2), duration_min=120, booked=booked,
                                      booked_price=Decimal("50.00") if booked else None,
                                      booked_currency="EUR" if booked else None, booking_code=code,
                                      legs=[Leg(seq=0, mode="train", carrier="NS", service_no="IC 777",
                                                from_name="A", to_name="B", depart_at=NOW + timedelta(days=3),
                                                depart_offset_min=60, arrive_at=NOW + timedelta(days=3, hours=2),
                                                arrive_offset_min=60)])]
        Fare(itinerary=trip.itineraries[0], source="ns", latest_price=Decimal("50"), currency="EUR",
             latest_captured_at=NOW)
        s.add(trip)
        s.commit()
        return trip.id, trip.itineraries[0].id


def test_booking_code_shows_on_upcoming_and_in_print(client, sessions):
    _, it_id = add(sessions, code=CODE)
    assert f"Booking code: {CODE}" in client.get("/upcoming").text
    assert f"Booking code: {CODE}" in client.get(f"/upcoming?only={it_id}").text


def test_journey_without_code_shows_no_booking_code(client, sessions):
    _, it_id = add(sessions, code=None)
    assert "Booking code" not in client.get("/upcoming").text
    assert "Booking code" not in client.get(f"/upcoming?only={it_id}").text


def test_code_is_escaped_as_text(client, sessions):
    _, it_id = add(sessions, code="<b>X</b>")
    html = client.get(f"/upcoming?only={it_id}").text
    assert "Booking code: &lt;b&gt;X&lt;/b&gt;" in html
    assert "<b>X</b>" not in html


def test_shared_trip_page_has_no_code(client, sessions):
    trip_id, _ = add(sessions, code=CODE)
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": _csrf(client, trip_id)})
    link = re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1)
    shared = TestClient(app).get(link.removeprefix("http://testserver"))
    assert shared.status_code == 200
    assert CODE not in shared.text


def test_calendar_feed_has_no_code(client, sessions):
    add(sessions, code=CODE)
    with sessions() as s:
        token = new_feed_token(s)
        s.commit()
    feed = TestClient(app).get(f"/calendar/{token}.ics")
    assert feed.status_code == 200
    assert "BEGIN:VEVENT" in feed.text
    assert CODE not in feed.text
