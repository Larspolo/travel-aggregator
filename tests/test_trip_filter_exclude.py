"""The trip table hides the offers with an excluded mode or carrier, keeps the exclusions in the sort links (#182)."""

import copy

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def bus(price):
    o = copy.deepcopy(direct(price))
    o["legs"][0].update(mode="bus", service_no="FLX 1", carrier="Flixbus")
    return o


def train_and_bus(price):
    """A train from Köln to Zürich, then a bus from Zürich: one offer with a leg of each mode."""
    o = copy.deepcopy(direct(price))
    first = o["legs"][0]
    second = dict(first, mode="bus", carrier="Flixbus", service_no="FLX 2", from_name=first["to_name"],
                  to_name="München", depart_at="2026-12-20T14:00:00+01:00", arrive_at="2026-12-20T15:00:00+01:00")
    o["legs"] = [first, second]
    return o


def test_an_excluded_mode_hides_each_offer_with_a_leg_of_it(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), bus("100.00"), train_and_bus("120.00")])
    page = client.get(f"/trips/{trip_id}?exclude_mode=bus").text
    assert "FLX 1" not in page and "FLX 2" not in page
    assert "ICE 9" in page
    assert 'value="bus" checked' in page


def test_excluded_carriers_hide_their_offers(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), bus("100.00"), train_and_bus("120.00")])
    page = client.get(f"/trips/{trip_id}?exclude_carrier=Flixbus&exclude_carrier=RyanAir").text
    assert "FLX 1" not in page and "FLX 2" not in page
    assert "ICE 9" in page
    page = client.get(f"/trips/{trip_id}?exclude_carrier=Deutsche+Bahn").text
    assert "ICE 9" not in page and "FLX 1" in page
    assert 'value="Flix"' in page and 'value="Deutsche Bahn" checked' in page


def test_the_sort_links_keep_the_exclusions_and_none_hides_nothing(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), bus("100.00")])
    page = client.get(f"/trips/{trip_id}?exclude_mode=bus").text
    assert "exclude_mode=bus&amp;sort=price" in page
    page = client.get(f"/trips/{trip_id}").text
    assert "ICE 9" in page and "FLX 1" in page
    exclude_part = page.split('<details class="exclude">')[1].split("</details>")[0]
    assert "checked" not in exclude_part
