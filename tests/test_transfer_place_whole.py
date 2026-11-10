"""The transfer place markup on the trip page: the part of the breakdown, the re-rank and the other offers (#1880, epic #1849)."""

import re

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

PLACE = "?transfer_place1_name=Mannheim%20Hbf&transfer_place1_markup="


def _row(page, service_no):
    return next(part for part in page.split("<tr") if f"DB {service_no}" in part)


def _cost(page, service_no):
    return re.search(r"= €(-?[\d.]+)", _row(page, service_no)).group(1)


def _pair(client, auth, trip_id):
    # 105 instead of the 110 of test_transfer_place_form._two: with a discount of 10 the changed offer ties at 100
    # and a tie goes to the lower price, so it would not rank higher.
    other = offer("105.00", "ICE 9")
    other["legs"][0]["to_name"] = other["legs"][1]["from_name"] = "Mannheim Hbf"
    ingest(client, auth, trip_id, [offer("100.00", "ICE 1"), other])


def test_a_markup_at_the_place_shows_the_part_and_raises_that_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    _pair(client, auth, trip_id)
    plain = client.get(f"/trips/{trip_id}").text
    page = client.get(f"/trips/{trip_id}{PLACE}20").text
    assert "transfer at Mannheim Hbf" in _row(page, "ICE 9") and "€20 transfer at Mannheim Hbf" in _row(page, "ICE 9")
    assert int(float(_cost(page, "ICE 9"))) - int(float(_cost(plain, "ICE 9"))) == 20


def test_a_discount_at_the_place_lowers_that_offer_and_ranks_it_higher(trip):  # noqa: F811
    client, auth, trip_id = trip
    _pair(client, auth, trip_id)
    plain = client.get(f"/trips/{trip_id}").text
    page = client.get(f"/trips/{trip_id}{PLACE}-10").text
    assert "€-10 transfer at Mannheim Hbf" in _row(page, "ICE 9")
    assert int(float(_cost(plain, "ICE 9"))) - int(float(_cost(page, "ICE 9"))) == 10
    assert page.index("ICE 9") < page.index("ICE 1") and plain.index("ICE 1") < plain.index("ICE 9")


def test_the_other_offer_keeps_its_cost_and_has_no_part(trip):  # noqa: F811
    client, auth, trip_id = trip
    _pair(client, auth, trip_id)
    plain = client.get(f"/trips/{trip_id}").text
    for markup in ("20", "-10"):
        page = client.get(f"/trips/{trip_id}{PLACE}{markup}").text
        assert "transfer at Mannheim Hbf" not in _row(page, "ICE 1")
        assert _cost(page, "ICE 1") == _cost(plain, "ICE 1")
