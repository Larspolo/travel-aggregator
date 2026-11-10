"""The whole feature of the booking code (#1715): store the code, then the routes show it or keep it off (#1719)."""

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
CODE = "K7Q2XP"
# a future departure, so that /upcoming lists the booking
DEPART = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)


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


def _book(sessions):
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 777", from_name="A", to_name="B",
              depart_at=DEPART, depart_offset_min=120, arrive_at=DEPART + timedelta(hours=2), arrive_offset_min=120)
    trip = Trip(title="Code trip", origin_text="A", destination_text="B", status="planning", date_from=DEPART.date())
    it = Itinerary(fingerprint="code-whole", depart_at=DEPART, arrive_at=DEPART + timedelta(hours=2),
                   duration_min=120, booked=True, booked_price=Decimal("89"), booked_currency="EUR",
                   booked_at=DEPART - timedelta(days=5), legs=[leg])
    Fare(itinerary=it, source="ns", latest_price=Decimal("89"), currency="EUR", latest_captured_at=DEPART)
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def test_store_the_code_then_upcoming_shows_it_and_shared_and_feed_do_not(client, sessions):
    tid, iid = _book(sessions)
    r = client.post(f"/trips/{tid}/itineraries/{iid}/booking-code",
                    data={"code": CODE, "csrf_token": _csrf(client, tid)}, follow_redirects=False)
    assert r.status_code == 303

    # the owner sees the code on the Upcoming page and on its print layout
    assert f"Booking code: {CODE}" in client.get("/upcoming").text
    assert f"Booking code: {CODE}" in client.get(f"/upcoming?only={iid}").text

    # the shared link of the trip does not contain the code
    share = client.post(f"/trips/{tid}/share", data={"csrf_token": _csrf(client, tid)})
    link = re.search(r'<pre class="share-link">([^<]+)</pre>', share.text).group(1)
    shared = TestClient(app).get(link.removeprefix("http://testserver"))
    assert shared.status_code == 200
    assert CODE not in shared.text

    # the calendar feed does not contain the code
    with sessions() as s:
        token = new_feed_token(s)
        s.commit()
    feed = TestClient(app).get(f"/calendar/{token}.ics")
    assert feed.status_code == 200
    assert "BEGIN:VEVENT" in feed.text
    assert CODE not in feed.text
