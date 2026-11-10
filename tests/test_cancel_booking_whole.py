"""The whole feature of the epic "cancel booking" (#1687): book, cancel with a refund, then the routes show it."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

PASSWORD = "pw"
# a future departure, so that /upcoming lists the booking; the year of the summary is the year of this departure
DEPART = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)


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
    trip = Trip(title="Whole", origin_text="A", destination_text="B", status="planning", date_from=DEPART.date())
    it = Itinerary(fingerprint="whole", depart_at=DEPART, arrive_at=DEPART + timedelta(hours=2), duration_min=120,
                   booked=True, booked_price=Decimal("89"), booked_currency="EUR",
                   booked_at=DEPART - timedelta(days=5), legs=[leg])
    Fare(itinerary=it, source="ns", latest_price=Decimal("89"), currency="EUR", latest_captured_at=DEPART)
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id


def _spend_2026(client):
    html = client.get("/upcoming/years").text
    block = re.search(rf'<section class="card year-summary"><h2>{DEPART.year}</h2>.*?</section>', html, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block.group(0)))


def test_book_cancel_with_refund_then_the_routes_show_the_refund(client, sessions):
    tid, iid = _book(sessions)
    assert f"only={iid}" in client.get("/upcoming").text
    page = client.get(f"/trips/{tid}").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post(f"/trips/{tid}/itineraries/{iid}/cancel", data={"csrf_token": token, "refund": "60"},
                    follow_redirects=False)
    assert r.status_code == 303

    assert f"only={iid}" not in client.get("/upcoming").text
    assert "Booking cancelled: paid €89.00, refund €60.00" in client.get(f"/trips/{tid}").text

    summary = _spend_2026(client)
    assert "29.00" in summary
    assert "0 journeys" in summary
    assert "Train: 0 journeys · €29.00 paid" in summary
