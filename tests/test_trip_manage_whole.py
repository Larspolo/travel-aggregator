"""The whole trip-management feature (#198): on the trip page the owner pins, hides, marks as booked and writes a note
on the offers of one trip (#199, #200, #201, #202). Four offers, one of each action."""

import re
from decimal import Decimal

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _id_at(sessions, trip_id, price):
    with sessions() as s:
        rows = s.query(Itinerary).filter_by(trip_id=trip_id).all()
        return next(it.id for it in rows if min(f.latest_price for f in it.fares) == Decimal(price))


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def _post(client, trip_id, itinerary, action, token, **data):
    r = client.post(f"/trips/{trip_id}/itineraries/{itinerary}/{action}", data={"csrf_token": token, **data},
                    follow_redirects=False)
    assert r.status_code == 303


def test_pin_hide_booked_and_note_work_together_on_the_trip_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105"), offer("99.90", "ICE 123"),
                                   offer("109.90", "ICE 131"), offer("119.90", "ICE 141")])
    hidden, booked, noted, pinned = (_id_at(sessions, trip_id, p) for p in ("89.90", "99.90", "109.90", "119.90"))
    token = _csrf(client, trip_id)
    _post(client, trip_id, pinned, "pin", token)  # the most expensive offer goes first
    _post(client, trip_id, hidden, "hide", token)
    _post(client, trip_id, booked, "booked", token)
    _post(client, trip_id, noted, "note", token, note="met Anna at the station")

    page = client.get(f"/trips/{trip_id}").text
    # the pinned row is first, although it has the highest price
    assert page.index("€119.90") < page.index("€99.90") < page.index("€109.90")
    # the hidden row shows only with show_hidden=true
    assert "€89.90" not in page
    shown = client.get(f"/trips/{trip_id}?show_hidden=true").text
    assert "€89.90" in shown and "hidden</span>" in shown
    # the booked row shows the mark, and only that row
    assert page.count("booked</span>") == 1
    assert "€99.90" in _row_with(page, "booked</span>")
    # the note shows in its row
    assert "€109.90" in _row_with(page, "met Anna at the station")


def _row_with(page, text):
    """The table row (the text from its <tr> to the next one) that holds text."""
    return next(chunk for chunk in page.split("<tr")[1:] if text in chunk)
