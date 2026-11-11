"""The cancel time of a booked journey through the routes (#2314): the owner types it on the trip page, and the trip
page, the Upcoming page and its print show it, with the chip "cancel soon or keep" in the 48 hours before it."""

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
CET = timezone(timedelta(hours=1))
DEPART = datetime(2026, 12, 20, 8, 0, tzinfo=CET)  # Amsterdam, 08:00 local


@pytest.fixture
def now(monkeypatch):
    """The clock of the departed offers and of the Upcoming page; a test sets `now["at"]`."""
    holder = {"at": datetime(2026, 12, 10, 10, 0, tzinfo=CET)}
    monkeypatch.setattr(departed, "clock", lambda: holder["at"])
    return holder


@pytest.fixture
def client(sessions, monkeypatch, now):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(sessions):
    leg = Leg(seq=0, mode="train", carrier="DB", service_no="ICE 1", from_name="Amsterdam", to_name="Berlin",
              depart_at=DEPART, depart_offset_min=60, arrive_at=DEPART + timedelta(hours=6), arrive_offset_min=60)
    trip = Trip(title="Amsterdam Berlin", origin_text="Amsterdam", destination_text="Berlin", status="planning",
                date_from=DEPART.date())
    it = Itinerary(fingerprint="ams-ber", depart_at=DEPART, arrive_at=DEPART + timedelta(hours=6), duration_min=360,
                   legs=[leg])
    Fare(itinerary=it, source="db", latest_price=Decimal("90"), currency="EUR", latest_captured_at=DEPART)
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id, it.fares[0].id


def post(client, page, url, **data):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(page).text).group(1)
    return client.post(url, data={"csrf_token": token, **data}, follow_redirects=False)


def book(client, tid, iid, fid):
    base = f"/trips/{tid}/itineraries/{iid}"
    post(client, f"/trips/{tid}", f"{base}/booked")
    assert post(client, f"/trips/{tid}", f"{base}/paid", fare_id=str(fid), price="90").status_code == 303


def test_the_cancel_time_shows_on_the_trip_page_and_the_upcoming_page_with_the_48_hour_chip(client, sessions, now):
    tid, iid, fid = add(sessions)
    book(client, tid, iid, fid)
    url = f"/trips/{tid}/itineraries/{iid}/cancel-by"
    assert post(client, f"/trips/{tid}", url, cancel_by="2026-12-18T18:00").status_code == 303

    assert "Cancel until 18 Dec 18:00" in client.get(f"/trips/{tid}").text
    assert "Cancel until 18 Dec 18:00" in client.get(f"/upcoming?only={iid}").text

    now["at"] = datetime(2026, 12, 17, 12, 0, tzinfo=CET)  # 30 hours before the cancel time
    assert "Cancel until 18 Dec 18:00" in client.get("/upcoming").text
    assert "cancel soon or keep" in client.get("/upcoming").text
    assert "cancel soon or keep" not in client.get(f"/upcoming?only={iid}").text  # the print shows no chip

    now["at"] = datetime(2026, 12, 19, 12, 0, tzinfo=CET)  # after the cancel time
    page = client.get("/upcoming").text
    assert "Cancel until 18 Dec" not in page
    assert "cancel soon or keep" not in page


def test_a_blank_cancel_time_is_shown_on_no_page(client, sessions, now):
    tid, iid, fid = add(sessions)
    book(client, tid, iid, fid)
    url = f"/trips/{tid}/itineraries/{iid}/cancel-by"
    assert post(client, f"/trips/{tid}", url, cancel_by="2026-12-18T18:00").status_code == 303
    assert post(client, f"/trips/{tid}", url, cancel_by="").status_code == 303

    now["at"] = datetime(2026, 12, 17, 12, 0, tzinfo=CET)  # the line would show here if it were stored
    for page in (f"/trips/{tid}", f"/upcoming?only={iid}", "/upcoming"):
        text = client.get(page).text
        assert "Cancel until 18 Dec" not in text, page
        assert "cancel soon or keep" not in text, page
