"""The paid price shows on each page after a later capture: the trip page, the Upcoming page and the JSON export (#1151,
epic #1145)."""

import copy
import json

from app import tokens
from tests.test_trip_booked import _itinerary_id, booked_url, csrf
from tests.test_trip_booked import trip as booked_trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_page import BODY, offer
from tests.test_upcoming_paid import text


def _ingest_later(sessions, client, trip_id, price):
    """The same connection with a new price: the same itinerary, a new capture of its fare."""
    with sessions() as s:
        token = tokens.create(s, "later capture")
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[offer(price, "ICE 105")])
    assert client.post("/api/ingest", json=body, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_the_paid_price_shows_on_the_trip_page_the_upcoming_page_and_the_export(
        sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    it = _itinerary_id(sessions, trip_id)
    # the owner books the row at 89.90
    r = client.post(booked_url(trip_id, it), data={"csrf_token": csrf(client, trip_id)}, follow_redirects=False)
    assert r.status_code == 303

    # a later capture of the same connection at 120.00
    _ingest_later(sessions, client, trip_id, "120.00")

    trip_page = client.get(f"/trips/{trip_id}").text
    assert "Paid €89.90" in trip_page
    assert "now €120" in trip_page and "+€30.10" in trip_page

    upcoming = text(client.get("/upcoming").text)
    assert "Paid €89.90" in upcoming
    assert "Total paid: €89.90" in upcoming

    export = json.loads(client.get(f"/trips/{trip_id}/export.json").text)
    booked = [i for i in export["itineraries"] if i.get("booked")]
    assert len(booked) == 1
    assert str(booked[0]["booked_price"]) in ("89.90", "89.9")
