"""The trip page and the Pinned page show the timetable change of a booked journey (#2341, epic #2339)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"
CET = timezone(timedelta(minutes=60))
SEEN = datetime(2026, 11, 1, tzinfo=timezone.utc)
MARK = "Timetable changed: ICE 145 now 08:42 → 14:55 (was 08:15 → 14:28)"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def at(hour, minute, day=20):
    return datetime(2026, 12, day, hour, minute, tzinfo=CET)


def itinerary(fp, dep, arr, seen, carrier="DB Fernverkehr AG", no="ICE 145", booked=False, pinned=False):
    it = Itinerary(fingerprint=fp, depart_at=dep, arrive_at=arr, duration_min=int((arr - dep).total_seconds() // 60),
                   booked=booked, pinned=pinned, last_seen_at=seen)
    it.legs = [Leg(seq=0, mode="train", carrier=carrier, service_no=no, from_name="Amsterdam", to_name="Basel",
                   depart_at=dep, depart_offset_min=60, arrive_at=arr, arrive_offset_min=60)]
    return it


def add_trip(sessions, newer=None):
    with sessions() as s:
        trip = Trip(title="Basel trip", status="planning")
        old = itinerary("old", at(8, 15), at(14, 28), SEEN, booked=True, pinned=True)
        trip.itineraries = [old] + ([newer] if newer is not None else [])
        s.add(trip)
        s.commit()
        return trip.id


def changed():
    return itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1), carrier="DB")


def same():
    return itinerary("new", at(8, 15), at(14, 28), SEEN + timedelta(days=1))


def squash(text):
    return re.sub(r"\s+", " ", text)


def test_trip_page_shows_the_timetable_change(client, sessions):
    trip_id = add_trip(sessions, changed())
    assert MARK in squash(client.get(f"/trips/{trip_id}").text)


def test_pinned_page_shows_the_timetable_change(client, sessions):
    add_trip(sessions, changed())
    assert MARK in squash(client.get("/pinned").text)


def test_trip_page_without_change_shows_no_mark(client, sessions):
    trip_id = add_trip(sessions, same())
    assert "Timetable changed" not in client.get(f"/trips/{trip_id}").text


def test_pinned_page_without_change_shows_no_mark(client, sessions):
    add_trip(sessions, same())
    assert "Timetable changed" not in client.get("/pinned").text
