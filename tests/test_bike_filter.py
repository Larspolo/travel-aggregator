"""A bicycle trip hides the rows whose fares all have "no bicycle" (#2474)."""

import copy
import html
import re

from app.models import Trip
from tests.test_filtered_best import _line
from tests.test_ingest_api import BODY
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

LATE = [("2026-12-20T11:00:00+01:00", "2026-12-20T15:00:00+01:00")]


def _post(client, auth, trip_id, source, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=offers)
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _offer(service, price, bike, times=PASS, carrier="DB"):
    o = itinerary(service, price, times, carrier=carrier)
    o["bike"] = bike
    return o


def _bike_trip(sessions, trip_id, value=True):
    with sessions() as s:
        s.get(Trip, trip_id).bike = value
        s.commit()


def _filtered(page):
    m = re.search(r'<p id="trip-filtered"[^>]*>(.*?)</p>', page, re.S)
    return html.unescape(m.group(1))


def _flix_trip(client, auth, sessions, trip_id):
    _bike_trip(sessions, trip_id)
    _post(client, auth, trip_id, "bahn.de", [_offer("ICE 1", "90.00", "allowed")])
    _post(client, auth, trip_id, "flixbus.de", [_offer("FLX 9", "20.00", "no", LATE, "FlixBus")])


def test_a_row_with_only_a_no_fare_is_hidden_by_bicycle(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _flix_trip(client, auth, sessions, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert "ICE 1" in page and "FLX 9" not in page
    line = _filtered(page)
    assert "Filters hide 1 of 2 offers" in line and "bicycle</a> hides 1" in line
    link = re.search(r'href="([^"]+)">bicycle', line).group(1)
    assert "bike=0" in link
    assert "FLX 9" in client.get(link).text


def test_a_trip_without_bicycle_hides_nothing(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _flix_trip(client, auth, sessions, trip_id)
    _bike_trip(sessions, trip_id, False)
    page = client.get(f"/trips/{trip_id}").text
    assert "FLX 9" in page and "bicycle</a>" not in page


def test_a_reservation_fare_of_another_source_is_the_main_fare(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _bike_trip(sessions, trip_id)
    _post(client, auth, trip_id, "flixbus.de", [_offer("ICE 1", "20.00", "no")])
    _post(client, auth, trip_id, "bahn.de", [_offer("ICE 1", "90.00", "reservation")])
    page = client.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0").text
    assert "ICE 1" in page and "€90.00" in page
    assert not _filtered(page).strip()


def test_the_best_hidden_offer_names_bicycle(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _flix_trip(client, auth, sessions, trip_id)
    line = _line(client.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0").text)
    assert "Best hidden offer: €20.00" in line and "hidden by bicycle" in line
    assert "bike=0" in re.search(r'href="([^"]+)">Show it', line).group(1)
