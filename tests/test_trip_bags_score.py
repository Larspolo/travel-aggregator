"""The checked bag of a trip in the baggage part of the score (#2398): "none" gives no bag cost."""

from decimal import Decimal
from types import SimpleNamespace

from app.door import baggage_extras
from app.models import Trip
from app.ranking import Weights
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

W40 = Weights(baggage_fee=Decimal("40"))
NONE = SimpleNamespace(checked_bag="none")


def _it(*modes, the_trip=None):
    return SimpleNamespace(legs=[SimpleNamespace(mode=m) for m in modes], trip=the_trip)


def _fare(included=None, price=None, currency="EUR"):
    return SimpleNamespace(checked_bags_included=included, checked_bag_price=price, currency=currency)


def test_no_trip_bag_keeps_the_estimate():
    assert baggage_extras(_fare(), _it("flight"), W40) == (("baggage (estimate)", Decimal("40")),)
    assert baggage_extras(_fare(), _it("flight", the_trip=SimpleNamespace(checked_bag=None)), W40) == (
        ("baggage (estimate)", Decimal("40")),)


def test_none_trip_gives_no_bag_part_without_bag_data():
    assert baggage_extras(_fare(), _it("flight", the_trip=NONE), W40) == (("no checked bag (trip)", Decimal(0)),)


def test_none_trip_ignores_an_included_bag_and_a_bag_price():
    assert baggage_extras(_fare(1), _it("flight", the_trip=NONE), W40) == (("no checked bag (trip)", Decimal(0)),)
    assert baggage_extras(_fare(0, Decimal("25")), _it("flight", the_trip=NONE), W40) == (
        ("no checked bag (trip)", Decimal(0)),)


def test_none_trip_train_and_fee_zero_give_no_part():
    assert baggage_extras(_fare(), _it("train", the_trip=NONE), W40) == ()
    assert baggage_extras(_fare(), _it("flight", the_trip=NONE), Weights(baggage_fee=Decimal(0))) == ()


def _flight(price, no):
    o = direct(price)
    o["legs"][0].update(mode="flight", service_no=no)
    return o


def test_the_trip_page_shows_no_checked_bag_for_none(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_flight("100.00", "KL 1")])
    page = client.get(f"/trips/{trip_id}?baggage_fee=40").text
    assert "baggage (estimate)" in page and "no checked bag (trip)" not in page
    with sessions() as s:
        s.get(Trip, trip_id).checked_bag = "none"
        s.commit()
    page = client.get(f"/trips/{trip_id}?baggage_fee=40").text
    assert "€0 no checked bag (trip)" in page and "baggage (estimate)" not in page


def test_a_none_trip_shows_the_zero_part_in_the_breakdown():
    from app.ranking import Breakdown, format_breakdown
    b = Breakdown(price=Decimal(0), time_cost=Decimal(0), transfer_cost=Decimal(0), extras=(("no checked bag (trip)", Decimal(0)),), total=Decimal(0))
    assert format_breakdown(b) == "€0 no checked bag (trip) = €0"
