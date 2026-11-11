"""The count line "Filters hide N of M offers" names each of the six filter kinds that a test of #1451 did not cover:
the page with only that filter shows one hidden offer (#1483)."""

import copy
import re

from tests.test_stale_filter import _two_offers
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_ingest_api import BODY


def _page(client, url):
    return re.sub(r"</?a[^>]*>", "", client.get(url).text)  # the links of #1453 are not part of the line


def test_mode_counts_the_bus_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "90.00", PASS),
                                   itinerary("BUS 1", "80.00", PASS, mode="bus", carrier="FlixBus")])
    page = _page(client, f"/trips/{trip_id}?mode=train")
    assert "Filters hide 1 of 2 offers: mode train hides 1" in page


def test_source_counts_the_offer_of_the_other_source(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "90.00", PASS)])
    body = copy.deepcopy(BODY)  # a second capture of the same trip from another site
    body.update(trip_id=trip_id, source="flixbus.de", offers=[itinerary("BUS 1", "80.00", PASS, mode="bus",
                                                                         carrier="FlixBus")])
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200
    page = _page(client, f"/trips/{trip_id}?source=bahn.de")
    assert "Filters hide 1 of 2 offers: source bahn.de hides 1" in page


def test_max_duration_counts_the_offer_over_300_min(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [
        itinerary("PASS 1", "90.00", PASS),
        itinerary("LONG 1", "80.00", [("2026-12-20T09:00:00+01:00", "2026-12-20T14:30:00+01:00")]),  # 5 h 30 min
    ])
    page = _page(client, f"/trips/{trip_id}?max_duration_min=300")
    assert "Filters hide 1 of 2 offers: max duration 300 min hides 1" in page


def test_earliest_depart_counts_the_offer_before_0700(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [
        itinerary("PASS 1", "90.00", PASS),
        itinerary("EARLY 1", "80.00", [("2026-12-20T06:30:00+01:00", "2026-12-20T10:00:00+01:00")]),
    ])
    page = _page(client, f"/trips/{trip_id}?earliest_depart=07:00")
    assert "Filters hide 1 of 2 offers: depart after 07:00 hides 1" in page


def test_hide_stale_counts_the_stale_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    page = _page(client, f"/trips/{trip_id}?hide_stale=true")
    assert "Filters hide 1 of 2 offers: hide stale hides 1" in page


def test_day_counts_the_offer_of_the_next_day(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [
        itinerary("DAY 1", "90.00", [("2026-12-18T09:00:00+01:00", "2026-12-18T13:00:00+01:00")]),
        itinerary("NEXT 2", "80.00", [("2026-12-19T09:00:00+01:00", "2026-12-19T13:00:00+01:00")]),
    ])
    page = _page(client, f"/trips/{trip_id}?day=2026-12-18")
    assert "Filters hide 1 of 2 offers: day 2026-12-18 hides 1" in page
