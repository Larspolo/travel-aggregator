"""The mark "no faster offer for less" (#1856): no other shown offer is cheaper and faster."""

from decimal import Decimal as D

from app.pareto import pareto_ids
from tests.test_trip_hide import hide, itinerary_at
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

MARK = "no faster offer for less"


def test_pareto_ids():
    assert pareto_ids([]) == set()
    assert pareto_ids([(1, D("10"), 300), (2, D("50"), 100), (3, D("60"), 300)]) == {1, 2}
    assert pareto_ids([(1, D("10"), 100), (2, D("10"), 200), (3, D("10"), 100)]) == {1, 3}
    assert pareto_ids([(1, D("10"), 100), (2, D("5"), 100)]) == {2}
    assert pareto_ids([(1, D("10"), 100), (2, D("20"), 90), (3, D("30"), 80), (4, D("25"), 95)]) == {1, 2, 3}


def marked(page):
    """The prices of the table rows with the mark."""
    page = page[page.index('id="table"'):].split('id="price-hours"')[0]  # not the chart after the table (#1858)
    return sorted(p for p in ("€89.90", "€150.00", "€200.00")
                  for row in page.split("<tr")[1:] if p in row and MARK in row)


def three(client, auth, trip_id):
    # cheap and slow (472 min), dear and fast (240 min), dear and slow
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00"), offer("200.00", "ICE 7")])


def test_the_cheap_and_the_fast_offer_have_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    three(client, auth, trip_id)
    assert marked(client.get(f"/trips/{trip_id}").text) == ["€150.00", "€89.90"]
    assert marked(client.get(f"/trips/{trip_id}?hour_markup=90").text) == ["€150.00", "€89.90"]


def test_a_hidden_offer_has_no_mark(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    three(client, auth, trip_id)
    hide(client, trip_id, itinerary_at(sessions, trip_id, "89.90"))
    # the dear and slow offer is still beaten by the fast one, and the hidden one does not count
    assert marked(client.get(f"/trips/{trip_id}?show_hidden=true").text) == ["€150.00"]
