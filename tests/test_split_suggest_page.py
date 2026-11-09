"""The edit page shows the transfer places of the offers with a button "Split via" (#1459)."""

import copy
import html
import re

from sqlalchemy import select

from app.models import Trip
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

VIA = [("2026-12-20T09:00:00+01:00", "2026-12-20T11:00:00+01:00"),
       ("2026-12-20T11:30:00+01:00", "2026-12-20T14:00:00+01:00")]


def _via(service, place):
    o = itinerary(service, "80.00", VIA)
    o["legs"][0] = dict(copy.deepcopy(o["legs"][0]), to_name=place)
    o["legs"][1] = dict(copy.deepcopy(o["legs"][1]), from_name=place)
    return o


def _edit(client, trip_id):
    return html.unescape(client.get(f"/trips/{trip_id}/edit").text)


def test_the_button_splits_the_trip_via_the_transfer_place(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_via("ICE 1", "Köln Hbf"), _via("ICE 2", "Köln Hbf"), itinerary("D 1", "90", PASS)])
    page = _edit(client, trip_id)
    assert "Transfer places of your offers" in page and "Split via Köln Hbf (2 offers)" in page
    assert '<option value="Köln Hbf">' in page and 'list="via-places"' in page
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post(f"/trips/{trip_id}/split", data={"via": "Köln Hbf", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        titles = [t.title for t in s.scalars(select(Trip).where(Trip.split_of_id == trip_id).order_by(Trip.id))]
        parts = s.scalars(select(Trip.id).where(Trip.split_of_id == trip_id)).all()
    assert titles == ["Amsterdam → Köln Hbf", "Köln Hbf → Zürich"]
    assert "Split via Köln Hbf" not in _edit(client, trip_id)  # after the split
    assert "Transfer places of your offers" not in _edit(client, parts[0])  # a split trip


def test_a_trip_with_no_transfers_shows_no_list(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("D 1", "90.00", PASS)])
    page = _edit(client, trip_id)
    assert "Transfer places of your offers" not in page and "via-places" not in page
