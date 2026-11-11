"""Price at which an offer becomes the best (#1964, epic #1963)."""

from decimal import Decimal

from app.tradeoff import best_at_price

D = Decimal


def test_price_at_which_offer_is_as_cheap_as_best() -> None:
    assert best_at_price(D("140"), D("90"), D("156")) == D("74")


def test_result_of_zero_or_less_gives_none() -> None:
    assert best_at_price(D("40"), D("30"), D("80")) is None


def test_infinite_price_gives_none() -> None:
    assert best_at_price(D("140"), D("Infinity"), D("156")) is None


def test_infinite_total_gives_none() -> None:
    assert best_at_price(D("140"), D("90"), D("Infinity")) is None


def test_same_total_as_best_gives_own_price() -> None:
    assert best_at_price(D("140"), D("90"), D("140")) == D("90")
