"""The cancel time on the Upcoming page and its print (#2312): the line "Cancel until", and the chip
"cancel soon or keep" within 48 hours of the time."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import departed
from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip

PASSWORD = "pw"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
DEPART = NOW + timedelta(days=30)
CANCEL = DEPART - timedelta(days=2)  # stored in UTC; the local offset is +60 min
LINE = f"Cancel until {(CANCEL + timedelta(hours=1)):%-d %b %H:%M}"
CHIP = "cancel soon or keep"


@pytest.fixture
def clock(monkeypatch):
    at = {"now": NOW}
    monkeypatch.setattr(departed, "clock", lambda: at["now"])
    return at


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(sessions, cancel_by=CANCEL):
    with sessions() as s:
        trip = Trip(title="T", origin_text="A", destination_text="B", status="planning")
        it = Itinerary(fingerprint="f", depart_at=DEPART, arrive_at=DEPART + timedelta(hours=2), duration_min=120,
                       booked=True, booked_price=Decimal("50.00"), booked_currency="EUR",
                       cancel_by=cancel_by, cancel_by_offset_min=60 if cancel_by else None,
                       legs=[Leg(seq=0, mode="train", carrier="NS", service_no="1", from_name="A", to_name="B",
                                 depart_at=DEPART, depart_offset_min=60, arrive_at=DEPART + timedelta(hours=2),
                                 arrive_offset_min=60)])
        trip.itineraries = [it]
        Fare(itinerary=it, source="ns", latest_price=Decimal("50"), currency="EUR", latest_captured_at=NOW)
        s.add(trip)
        s.commit()
        return trip.id, it.id


def test_inside_48_hours_shows_line_and_chip(client, sessions, clock):
    add(sessions)
    clock["now"] = CANCEL - timedelta(hours=6)  # 17 Dec 12:00 local
    page = client.get("/upcoming").text
    assert LINE in page
    assert CHIP in page


def test_more_than_48_hours_shows_line_and_no_chip(client, sessions, clock):
    add(sessions)
    clock["now"] = CANCEL - timedelta(days=3)  # 15 Dec 12:00 local
    page = client.get("/upcoming").text
    assert LINE in page
    assert CHIP not in page


def test_after_the_time_shows_neither(client, sessions, clock):
    add(sessions)
    clock["now"] = CANCEL + timedelta(hours=18)  # 19 Dec 12:00 local
    page = client.get("/upcoming").text
    assert LINE not in page
    assert CHIP not in page


def test_print_shows_line_and_no_chip(client, sessions, clock):
    tid, iid = add(sessions)
    clock["now"] = CANCEL - timedelta(hours=6)
    page = client.get(f"/upcoming?only={iid}").text
    assert LINE in page
    assert CHIP not in page


def test_journey_without_cancel_time_shows_neither(client, sessions, clock):
    add(sessions, cancel_by=None)
    clock["now"] = CANCEL - timedelta(hours=6)
    page = client.get("/upcoming").text
    assert "Cancel until" not in page
    assert CHIP not in page
