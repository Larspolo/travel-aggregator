"""The whole feature `trip:delay-claim` through the routes (#1693): book at €90, type the delay on the trip page, see
the claim on the trip page and on "Travel per year", and mark it paid."""

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
DEPART = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setattr(departed, "clock", lambda: datetime.now(timezone.utc))
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(sessions, mode="train"):
    leg = Leg(seq=0, mode=mode, carrier="NS", service_no="1", from_name="A", to_name="B", depart_at=DEPART,
              depart_offset_min=60, arrive_at=DEPART + timedelta(hours=2), arrive_offset_min=60)
    trip = Trip(title=f"T {mode}", origin_text="A", destination_text="B", status="planning", date_from=DEPART.date())
    it = Itinerary(fingerprint=mode, depart_at=DEPART, arrive_at=DEPART + timedelta(hours=2), duration_min=120,
                   legs=[leg])
    Fare(itinerary=it, source="ns", latest_price=Decimal("90"), currency="EUR", latest_captured_at=DEPART)
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


def delay(client, tid, iid, minutes):
    assert post(client, f"/trips/{tid}", f"/trips/{tid}/itineraries/{iid}/delay", minutes=minutes).status_code == 303


def test_the_example_of_the_roadmap(client, sessions):
    tid, iid, fid = add(sessions)
    book(client, tid, iid, fid)
    delay(client, tid, iid, "75")
    assert "Claim €22.50 (25 % for a delay of 75 min)" in client.get(f"/trips/{tid}").text
    assert "Claim €22.50 (25 %)" in client.get("/upcoming/years").text
    post(client, "/upcoming/years", f"/upcoming/years/claims/{iid}/paid")
    assert "No open claims" in client.get("/upcoming/years").text
    assert "claim paid" in client.get(f"/trips/{tid}").text
    delay(client, tid, iid, "130")
    assert "Claim €45.00 (50 % for a delay of 130 min)" in client.get(f"/trips/{tid}").text
    delay(client, tid, iid, "40")
    assert "Claim €" not in client.get(f"/trips/{tid}").text


def test_a_bus_journey_has_no_claim(client, sessions):
    tid, iid, fid = add(sessions, mode="bus")
    book(client, tid, iid, fid)
    delay(client, tid, iid, "75")
    assert "Claim €" not in client.get(f"/trips/{tid}").text
    assert "No open claims" in client.get("/upcoming/years").text
