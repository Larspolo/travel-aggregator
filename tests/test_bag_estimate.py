"""The flat baggage fee is marked as an estimate in the breakdown (#2051)."""

from decimal import Decimal
from types import SimpleNamespace

from app.door import baggage_extras
from app.ranking import Weights
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

W30 = Weights(baggage_fee=Decimal("30"))


def _it(*modes):
    return SimpleNamespace(legs=[SimpleNamespace(mode=m) for m in modes])


def _fare(included=None, price=None, currency="EUR"):
    return SimpleNamespace(checked_bags_included=included, checked_bag_price=price, currency=currency)


def test_no_bag_data_is_an_estimate():
    assert baggage_extras(_fare(), _it("flight"), W30) == (("baggage (estimate)", Decimal("30")),)


def test_bag_price_of_the_fare_is_not_an_estimate():
    assert baggage_extras(_fare(0, Decimal("25.06")), _it("flight"), W30) == (("baggage", Decimal("25.06")),)


def test_included_bag_is_not_an_estimate():
    assert baggage_extras(_fare(1), _it("flight"), W30) == (("baggage (included)", Decimal(0)),)


def _flight(price, no, **bag):
    o = direct(price)
    o["legs"][0].update(mode="flight", service_no=no)
    o.update(bag)
    return o


def test_flat_fee_shows_estimate_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_flight("100.00", "KL 1")])
    page = client.get(f"/trips/{trip_id}?baggage_fee=30").text
    assert "€30 baggage (estimate)" in page
