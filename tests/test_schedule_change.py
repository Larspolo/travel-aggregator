"""A timetable change of a booked journey shows on the Upcoming page (#2340)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip
from app.schedule_change import schedule_changes

PASSWORD = "pw"
CET = timezone(timedelta(minutes=60))
NOW = datetime(2026, 12, 1, tzinfo=timezone.utc)
SEEN = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def at(hour, minute, day=20):
    return datetime(2026, 12, day, hour, minute, tzinfo=CET)


def itinerary(fp, dep, arr, seen, carrier="DB Fernverkehr AG", no="ICE 145", booked=False, cancelled=None):
    it = Itinerary(fingerprint=fp, depart_at=dep, arrive_at=arr, duration_min=int((arr - dep).total_seconds() // 60),
                   booked=booked, last_seen_at=seen, cancelled_at=cancelled)
    it.legs = [Leg(seq=0, mode="train", carrier=carrier, service_no=no, from_name="Amsterdam", to_name="Basel",
                   depart_at=dep, depart_offset_min=60, arrive_at=arr, arrive_offset_min=60)]
    return it


def setup(sessions, newer=None, no="ICE 145", **booked):
    with sessions() as s:
        trip = Trip(title="Basel", status="planning")
        old = itinerary("old", at(8, 15), at(14, 28), SEEN, no=no, booked=True, **booked)
        trip.itineraries = [old] + ([newer] if newer is not None else [])
        s.add(trip)
        s.commit()
        return old.id, schedule_changes(s, NOW)


def test_newer_capture_with_other_times_gives_one_change(client, sessions):
    old_id, changes = setup(sessions, itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1), carrier="DB"))
    assert len(changes[old_id]) == 1
    text = re.sub(r"\s+", " ", client.get("/upcoming").text)
    assert "Timetable changed: ICE 145 now 08:42 → 14:55 (was 08:15 → 14:28)" in text


@pytest.mark.parametrize("newer, booked", [
    (itinerary("new", at(8, 15), at(14, 28), SEEN + timedelta(days=1)), {}),
    (itinerary("new", at(8, 42, 21), at(14, 55, 21), SEEN + timedelta(days=1)), {}),
    (itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1), no="ICE 147"), {}),
    (itinerary("new", at(8, 42), at(14, 55), SEEN - timedelta(days=1)), {}),
    (itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1), carrier="ÖBB"), {}),
    (itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1)), {"cancelled": SEEN}),
], ids=["same-times", "other-day", "other-number", "older", "other-carrier", "cancelled"])
def test_no_change(sessions, newer, booked):
    _, changes = setup(sessions, newer, **booked)
    assert changes == {}


def test_leg_with_no_service_number_gives_no_change(sessions):
    _, changes = setup(sessions, itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1), no=None), no=None)
    assert changes == {}
