"""The calendar feed of all booked journeys at a secret link (#1112)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_token, token_limiter
from app.calendar_feed import KEY, new_feed_token, revoke_feed
from app.main import app
from app.models import Itinerary, Setting
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


@pytest.fixture(autouse=True)
def _limiter():
    token_limiter.reset()
    yield
    token_limiter.reset()


def _token(sessions) -> str:
    with sessions() as s:
        token = new_feed_token(s)
        s.commit()
    return token


def _set(sessions, trip_id, booked_arrivals):
    """Give each itinerary of the trip (by id) a booked state and an arrival shift (days from now)."""
    now = datetime.now(timezone.utc)
    with sessions() as s:
        its = s.query(Itinerary).filter_by(trip_id=trip_id).order_by(Itinerary.id).all()
        for it, (booked, days) in zip(its, booked_arrivals, strict=True):
            it.booked = booked
            it.arrive_at = now + timedelta(days=days)
            it.note = "secret note"
        s.commit()
        return [it.id for it in its]


def test_a_valid_token_gives_the_booked_legs_in_the_window(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90", "ICE 1"), offer("99.90", "ICE 2"), offer("77.70", "ICE 3")])
    ids = _set(sessions, tid, [(True, -10), (False, 5), (True, -31)])
    token = _token(sessions)
    r = TestClient(app).get(f"/calendar/{token}.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"
    text = r.text
    assert "X-WR-CALNAME:travel-aggregator" in text and "REFRESH-INTERVAL;VALUE=DURATION:PT6H" in text
    with sessions() as s:
        legs = s.get(Itinerary, ids[0]).legs
        assert text.count("BEGIN:VEVENT") == len(legs) == 2
        for leg in legs:
            assert f"UID:leg-{leg.id}@travel-aggregator" in text
    assert "ICE 1" in text and "ICE 2" not in text and "ICE 3" not in text
    assert "secret note" not in text and "89.90" not in text and "EUR" not in text


def test_bad_revoked_and_old_tokens_give_404(trip, sessions):  # noqa: F811
    client = TestClient(app)
    assert client.get("/calendar/nothing.ics").status_code == 404
    old = _token(sessions)
    new = _token(sessions)
    assert client.get(f"/calendar/{old}.ics").status_code == 404
    assert client.get(f"/calendar/{new}.ics").status_code == 200
    with sessions() as s:
        assert s.get(Setting, KEY).value == hash_token(new) != new
        revoke_feed(s)
        s.commit()
    assert client.get(f"/calendar/{new}.ics").status_code == 404


def test_twenty_bad_tokens_give_429(trip, sessions):  # noqa: F811
    token = _token(sessions)
    bad = TestClient(app, client=("198.51.100.8", 50000))
    for i in range(token_limiter.ADDRESS_MAX):
        assert bad.get(f"/calendar/bad-{i}.ics").status_code == 404
    r = bad.get(f"/calendar/{token}.ics")
    assert r.status_code == 429 and r.headers["retry-after"] == "900"
