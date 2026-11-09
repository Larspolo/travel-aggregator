"""The bags of the fare in the baggage part of the score (#1527)."""

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


def test_included_bag_is_zero():
    assert baggage_extras(_fare(1), _it("flight"), W30) == (("baggage (included)", Decimal(0)),)


def test_bag_price_of_the_fare():
    assert baggage_extras(_fare(0, Decimal("25.06")), _it("flight"), W30) == (("baggage", Decimal("25.06")),)


def test_bag_price_in_other_currency_and_no_rate():
    assert baggage_extras(_fare(None, Decimal("100"), "CZK"), _it("flight"), W30, {"CZK": Decimal("0.04")}) == (
        ("baggage", Decimal("4.00")),)
    assert baggage_extras(_fare(None, Decimal("100"), "CZK"), _it("flight"), W30) == (("baggage", Decimal("30")),)


def test_no_bag_data_gives_the_flat_fee():
    assert baggage_extras(_fare(), _it("flight"), W30) == (("baggage", Decimal("30")),)


def test_train_and_fee_zero_give_no_part():
    assert baggage_extras(_fare(), _it("train"), W30) == ()
    assert baggage_extras(_fare(1), _it("flight"), Weights(baggage_fee=Decimal(0))) == ()
    assert baggage_extras(_fare(), _it("flight"), Weights(baggage_fee=Decimal(0))) == ()


def _flight(price, no, **bag):
    o = direct(price)
    o["legs"][0].update(mode="flight", service_no=no)
    o.update(bag)
    return o


def test_included_bag_ranks_first_at_the_same_price(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_flight("100.00", "KL 1"), _flight("100.00", "KL 2", checked_bags_included=1)])
    page = client.get(f"/trips/{trip_id}?baggage_fee=30").text
    assert "€0 baggage (included)" in page and "€30 baggage" in page
    assert page.index("KL 2") < page.index("KL 1")
