"""The hard filters of the trip table work together, and a penalty ranks an offer lower (#183)."""

import copy

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_table_highlights import badges

FILTERS = "max_transfers=1&max_duration_min=300&earliest_depart=07:00&latest_arrive=22:00&exclude_mode=bus&exclude_carrier=FlixBus"


def itinerary(service, price, times, mode="train", carrier="DB"):
    """One offer with one leg per (depart, arrive) pair, local times with their offset."""
    o = copy.deepcopy(offer(price, service, carrier))
    o["legs"] = [dict(o["legs"][0], depart_at=d, arrive_at=a, mode=mode, carrier=carrier) for d, a in times]
    return o


PASS = [("2026-12-20T09:00:00+01:00", "2026-12-20T13:00:00+01:00")]


def test_only_the_offer_that_passes_all_filters_shows(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [
        itinerary("PASS 1", "150.00", PASS),
        # each offer is outside one filter only
        itinerary("TWO 1", "90.00", [("2026-12-20T09:00:00+01:00", "2026-12-20T10:00:00+01:00"),
                                     ("2026-12-20T10:30:00+01:00", "2026-12-20T11:30:00+01:00"),
                                     ("2026-12-20T12:00:00+01:00", "2026-12-20T13:00:00+01:00")]),  # 2 transfers
        itinerary("LONG 1", "90.00", [("2026-12-20T09:00:00+01:00", "2026-12-20T17:00:00+01:00")]),  # 8 hours
        itinerary("EARLY 1", "90.00", [("2026-12-20T05:30:00+01:00", "2026-12-20T09:30:00+01:00")]),  # 05:30
        itinerary("LATE 1", "90.00", [("2026-12-20T20:00:00+01:00", "2026-12-20T23:40:00+01:00")]),  # 23:40
        itinerary("BUS 1", "90.00", [("2026-12-20T09:00:00+01:00", "2026-12-20T13:00:00+01:00")],
                  mode="bus", carrier="FlixBus"),
    ])
    page = client.get(f"/trips/{trip_id}?{FILTERS}").text
    assert "PASS 1" in page
    for hidden in ("TWO 1", "LONG 1", "EARLY 1", "LATE 1", "BUS 1"):
        assert hidden not in page
    rows = badges(page)
    assert len(rows) == 1 and "cheapest" in rows[0]  # the one row carries the badges


def test_a_penalty_without_a_time_filter_ranks_the_early_offer_lower(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [
        itinerary("EARLY 2", "100.00", [("2026-12-20T05:30:00+01:00", "2026-12-20T09:30:00+01:00")]),
        itinerary("PASS 2", "150.00", PASS),
    ])
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("EARLY 2") < page.index("PASS 2")  # 100 + 4 h = 160: first with no penalty
    page = client.get(f"/trips/{trip_id}?time_window_penalty=100").text
    assert "EARLY 2" in page and "PASS 2" in page  # no filter: both show
    assert page.index("PASS 2") < page.index("EARLY 2")  # 160 + 100 = 260: lower than 210
