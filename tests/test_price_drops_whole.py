"""The price drops from the ingest to the trip page and the trips list (#357): one pinned fare dropped, one offer
that is not pinned dropped more. Only the pinned drop shows."""

import re

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def _pin_id(sessions, trip_id, service_no):
    with sessions() as s:
        return next(it.id for it in s.query(Itinerary).filter_by(trip_id=trip_id).all()
                    if it.legs[0].service_no == service_no)


def test_only_the_pinned_drop_shows_on_the_list_and_the_trip_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105"), offer("60.00", "ICE 123")])
    pinned = _pin_id(sessions, trip_id, "ICE 105")
    r = client.post(f"/trips/{trip_id}/itineraries/{pinned}/pin", data={"csrf_token": _csrf(client, trip_id)},
                    follow_redirects=False)
    assert r.status_code == 303
    client.get(f"/trips/{trip_id}")  # the view stores the seen prices
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105"), offer("30.00", "ICE 123")])

    # the trips list shows the drop of the pinned fare, not the larger drop of the unpinned offer
    listing = client.get("/").text
    assert "price dropped €20.00" in listing
    assert "price dropped €30.00" not in listing

    # the trip page shows the box with the pinned fare only
    page = client.get(f"/trips/{trip_id}").text
    assert "Price drops" in page and "price dropped EUR 20.00" in page
    assert "price dropped EUR 30.00" not in page

    # after the view, neither the list nor the page shows the drop again
    assert "price dropped" not in client.get("/").text
    again = client.get(f"/trips/{trip_id}").text
    assert "Price drops" not in again
    assert "price dropped" not in client.get("/").text


def test_the_unpinned_drop_alone_shows_nothing(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105"), offer("60.00", "ICE 123")])
    client.get(f"/trips/{trip_id}")
    ingest(client, auth, trip_id, [offer("30.00", "ICE 123")])
    assert "price dropped" not in client.get("/").text
    assert "Price drops" not in client.get(f"/trips/{trip_id}").text
