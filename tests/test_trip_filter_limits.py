"""The trip table hides the offers over a limit of transfers or duration (#180)."""

import copy

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def long_trip(price):
    """Two legs with a transfer, 5 hours 30 minutes in all."""
    o = copy.deepcopy(direct(price))
    first = dict(o["legs"][0], to_name="Basel SBB", depart_at="2026-12-20T09:00:00+01:00",
                 arrive_at="2026-12-20T10:00:00+01:00")
    second = dict(o["legs"][0], from_name="Basel SBB", depart_at="2026-12-20T10:30:00+01:00",
                  arrive_at="2026-12-20T14:30:00+01:00")
    o["legs"] = [first, second]
    return o


def test_max_transfers_zero_shows_only_direct_offers(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), long_trip("120.00")])
    page = client.get(f"/trips/{trip_id}?max_transfers=0").text
    assert "= €210" in page  # the direct offer: 150 + 4 h
    assert "€120" not in page and "€190" not in page  # the offer with a transfer is hidden


def test_max_duration_hides_the_longer_offers(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), long_trip("120.00")])
    page = client.get(f"/trips/{trip_id}?max_duration_min=300").text  # 5 hours
    assert "= €210" in page  # 4 hours: shown
    assert "€120" not in page  # 5 h 30 min: hidden


def test_no_limit_shows_all_offers(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), long_trip("120.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert page.count("= €") == 2  # both offers, no limit
    page_empty = client.get(f"/trips/{trip_id}?max_transfers=&max_duration_min=").text  # the empty boxes of the form
    assert page_empty.count("= €") == 2


def test_a_sort_link_keeps_the_limits(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), long_trip("120.00")])
    page = client.get(f"/trips/{trip_id}?max_transfers=0&max_duration_min=300").text
    assert "max_transfers=0" in page and "max_duration_min=300" in page
