"""Tests of the break-even hour value of two offers (#893)."""

from decimal import Decimal

from app.tradeoff import BreakEven, break_even

D = Decimal
H = D("10")
INF = D("Infinity")


def test_break_even_of_two_offers() -> None:
    # a: 100 EUR and 5 h; x: 125 EUR and 3 h, at 10 EUR per hour.
    result = break_even(D("150"), D("155"), D("155"), D("158"), H)
    assert result == BreakEven(D("12.50"), "above")


def test_equal_slopes_give_none() -> None:
    assert break_even(D("150"), D("155"), D("160"), D("165"), H) is None


def test_negative_break_even_gives_none() -> None:
    # 10 + (200 - 100) / (5 - 10) = -10: no hour value >= 0 makes the offers equal.
    assert break_even(D("100"), D("105"), D("200"), D("210"), H) is None


def test_slower_and_cheaper_x_is_better_below() -> None:
    # x is cheaper now (140 < 150) but its slope is larger (slower): x wins below 20 EUR per hour.
    result = break_even(D("150"), D("155"), D("140"), D("146"), H)
    assert result == BreakEven(D("20.00"), "below")


def test_infinite_total_gives_none() -> None:
    assert break_even(INF, INF, D("155"), D("158"), H) is None
    assert break_even(D("150"), D("155"), INF, INF, H) is None
