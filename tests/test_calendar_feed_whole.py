"""The calendar feed follows the bookings (#1114): a booked journey is in the next response, an unbooked one is not,
the feed holds no note, token or price (P5), and "Revoke" on the Upcoming page gives 404 (#1112, #1113)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login, token_limiter
from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer


@pytest.fixture
def whole(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    token_limiter.reset()
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, token
    app.dependency_overrides.pop(require_login, None)
    token_limiter.reset()


def _csrf(client, path) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _prepare(sessions, trip_id):
    """Give the one itinerary an arrival in the window and a note; return its id and the UIDs of its legs."""
    with sessions() as s:
        it = s.query(Itinerary).filter_by(trip_id=trip_id).one()
        it.arrive_at = datetime.now(timezone.utc) + timedelta(days=5)
        it.booked = False
        it.note = "secret note"
        s.commit()
        uids = [f"UID:leg-{leg.id}@travel-aggregator" for leg in it.legs]
        return it.id, uids


def test_the_feed_follows_the_bookings_and_revoke_stops_it(whole, sessions):
    client, auth, trip_id, ingest_token = whole
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    it_id, uids = _prepare(sessions, trip_id)
    assert uids

    r = client.post("/upcoming/calendar", data={"csrf_token": _csrf(client, "/upcoming")})
    link = re.search(r'value="(http[^"]+/calendar/[^"]+\.ics)"', r.text).group(1)
    path = link.split("testserver", 1)[1]
    anon = TestClient(app)

    before = anon.get(path)
    assert before.status_code == 200 and not any(uid in before.text for uid in uids)

    book = f"/trips/{trip_id}/itineraries/{it_id}/booked"
    client.post(book, data={"csrf_token": _csrf(client, f"/trips/{trip_id}")})
    booked = anon.get(path).text
    assert all(uid in booked for uid in uids)

    client.post(book, data={"csrf_token": _csrf(client, f"/trips/{trip_id}")})
    unbooked = anon.get(path).text
    assert not any(uid in unbooked for uid in uids)

    for text in (booked, unbooked):
        assert "secret note" not in text
        assert ingest_token not in text
        assert "89.90" not in text and "EUR" not in text

    client.post("/upcoming/calendar/revoke", data={"csrf_token": _csrf(client, "/upcoming")})
    assert anon.get(path).status_code == 404
