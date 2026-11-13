"""A part-price fare shows the mark and does not give the best offer or a split pair (#2656)."""
from decimal import Decimal

import pytest

from app.models import Fare, Itinerary, Trip
from app.ranking import Weights
from app.web.pages import best_for_weights
from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client)
from tests.test_split_page import _offer, _split
from tests.test_trip_hide import itinerary_at
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

BADGE = 'class="badge part-price"'


def _part(o):
    o["part_price"] = True
    return o


@pytest.fixture
def two(trip, sessions):  # noqa: F811
    tclient, auth, tid = trip
    ingest(tclient, auth, tid, [_part(offer("39.90", "ICE 1")), offer("119.90", "ICE 2")])
    return tclient, auth, tid, itinerary_at(sessions, tid, "39.90"), itinerary_at(sessions, tid, "119.90")


def _row(page, it_id):
    row = page[page.index(f'id="it-{it_id}"'):]
    return row[:row.index("</tr>")]


def test_a_cheap_part_price_row_is_second_and_not_the_best(two, sessions):
    tclient, _, tid, part, full = two
    page = tclient.get(f"/trips/{tid}").text
    assert page.index(f'id="it-{full}"') < page.index(f'id="it-{part}"')
    assert BADGE in _row(page, part) and "price for a part of the route</span>" in _row(page, part)
    assert BADGE not in _row(page, full)
    assert "€39.90" in _row(page, part)  # the row keeps its cost
    with sessions() as s:
        best = best_for_weights(s, s.get(Trip, tid), Weights())
        assert best[0].id == full and best[1].latest_price == Decimal("119.90")


def test_a_full_fare_gives_the_cost_of_a_row_with_a_part_price_fare(trip, sessions):  # noqa: F811
    tclient, auth, tid = trip
    ingest(tclient, auth, tid, [_part(offer("40.00", "ICE 1", fare="Teilpreis")), offer("60.00", "ICE 1", fare="Flexpreis")])
    with sessions() as s:
        its = s.query(Itinerary).filter_by(trip_id=tid).all()
        assert len(its) == 1 and len(its[0].fares) == 2
        it_id = its[0].id
        best = best_for_weights(s, s.get(Trip, tid), Weights())
        assert best[1].latest_price == Decimal("60.00") and best[2].price == Decimal("60.00")
    page = tclient.get(f"/trips/{tid}").text
    row = _row(page, it_id)
    price = row[row.index('<td class="price">'):row.index('<td class="cost">')]
    assert "€60.00" in price and BADGE not in price
    assert BADGE in page[page.index('<div class="fares">'):]  # the mark on the part-price fare of the fare list


def test_with_only_part_price_fares_there_is_no_best_offer(trip, sessions):  # noqa: F811
    tclient, auth, tid = trip
    ingest(tclient, auth, tid, [_part(offer("39.90", "ICE 1"))])
    with sessions() as s:
        assert best_for_weights(s, s.get(Trip, tid), Weights()) is None


def test_a_split_suggestion_does_not_pair_a_part_price_fare(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    a, b = _split(c, sessions, trip_id)
    with sessions() as s:
        _offer(s, a, "Amsterdam", "Köln", 0, 3, "40", "ns")
        _offer(s, b, "Köln", "Zürich", 4, 5, "50", "db")
        s.commit()
    assert "Amsterdam → Köln (ns)" in c.get(f"/trips/{trip_id}").text
    with sessions() as s:
        for f in s.query(Fare).join(Itinerary, Fare.itinerary_id == Itinerary.id).filter(Itinerary.trip_id == a):
            f.part_price = True
        s.commit()
    assert "Amsterdam → Köln (ns)" not in c.get(f"/trips/{trip_id}").text
