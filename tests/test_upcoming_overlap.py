"""The Upcoming page warns about booked journeys in conflict, with a link to the other trip (#1654)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Trip

PASSWORD = "pw"
ZURICH = timezone(timedelta(minutes=60))
WARN = r'<p class="upcoming-conflict">.*?</p>'


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def trip_with(s, title, depart, arrive, previous_id=None, fingerprint=None):
    trip = Trip(title=title, status="planning", return_of_id=previous_id)
    trip.itineraries = [Itinerary(fingerprint=fingerprint or title, depart_at=depart, arrive_at=arrive,
                                  duration_min=int((arrive - depart).total_seconds() // 60), booked=True)]
    s.add(trip)
    s.commit()
    return trip.id, trip.itineraries[0].id


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2031, 12, day, hour, minute, tzinfo=ZURICH)


def test_order_conflict_warns_at_the_second_journey_with_a_link_to_the_first_trip(client, sessions):
    with sessions() as s:
        first_trip, _ = trip_with(s, "Outbound", at(1, 10), at(1, 16, 2), fingerprint="out")
        second_trip, second = trip_with(s, "Return", at(1, 14), at(1, 18), previous_id=first_trip, fingerprint="back")
    html = client.get("/upcoming").text
    warnings = re.findall(WARN, html, re.S)
    assert len(warnings) == 1
    assert "This journey departs before the journey before it arrives" in warnings[0]
    assert f'<a href="/trips/{first_trip}">' in warnings[0]
    assert "overlaps another booked journey" not in html


def test_overlap_of_unlinked_trips_warns_at_each_journey(client, sessions):
    with sessions() as s:
        a, _ = trip_with(s, "Trip A", at(2, 10), at(2, 12), fingerprint="a")
        b, _ = trip_with(s, "Trip B", at(2, 11), at(2, 13), fingerprint="b")
    html = client.get("/upcoming").text
    warnings = re.findall(WARN, html, re.S)
    assert len(warnings) == 2
    assert all("This journey overlaps another booked journey" in w for w in warnings)
    assert f'<a href="/trips/{b}">' in warnings[0]  # Trip A's journey links to Trip B
    assert f'<a href="/trips/{a}">' in warnings[1]


def test_journeys_on_separate_days_show_no_warning(client, sessions):
    with sessions() as s:
        trip_with(s, "Day one", at(3, 10), at(3, 12), fingerprint="d1")
        trip_with(s, "Day two", at(4, 10), at(4, 12), fingerprint="d2")
    assert re.search(WARN, client.get("/upcoming").text, re.S) is None


def test_print_of_one_journey_shows_no_warning(client, sessions):
    with sessions() as s:
        a, _ = trip_with(s, "Trip A", at(2, 10), at(2, 12), fingerprint="a")
        _, b_it = trip_with(s, "Trip B", at(2, 11), at(2, 13), fingerprint="b")
    html = client.get(f"/upcoming?only={b_it}").text
    assert "Journey: Trip B" in html
    assert re.search(WARN, html, re.S) is None
    assert "overlaps another booked journey" not in html
