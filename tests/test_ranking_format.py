from decimal import Decimal

import pytest

from app.ranking import Breakdown, format_breakdown


def D(value: str) -> Decimal:
    return Decimal(value)


def test_example_of_ticket_prints_exactly():
    b = Breakdown(D("90.00"), D("62.00"), D("30.00"), D("182.00"))
    assert format_breakdown(b) == "€90 price + €62 time + €30 transfers = €182"


def test_zero_part_is_left_out():
    b = Breakdown(D("90.00"), D("62.00"), D("0.00"), D("152.00"))
    assert format_breakdown(b) == "€90 price + €62 time = €152"


def test_zero_price_is_left_out():
    b = Breakdown(D("0.00"), D("62.00"), D("30.00"), D("92.00"))
    assert format_breakdown(b) == "€62 time + €30 transfers = €92"


def test_all_parts_zero_prints_total_only():
    b = Breakdown(D("0.00"), D("0.00"), D("0.00"), D("0.00"))
    assert format_breakdown(b) == "€0"


def test_part_with_cents_shows_both_digits():
    b = Breakdown(D("90.50"), D("62.00"), D("0.00"), D("152.50"))
    assert format_breakdown(b) == "€90.50 price + €62 time = €152.50"


def test_cent_part_with_trailing_zero_keeps_two_digits():
    b = Breakdown(D("90.05"), D("0.10"), D("0.00"), D("90.15"))
    assert format_breakdown(b) == "€90.05 price + €0.10 time = €90.15"


@pytest.mark.parametrize("value,expected", [("7", "€7"), ("7.00", "€7"), ("7.5", "€7.50"), ("0.01", "€0.01")])
def test_amount_formats(value, expected):
    b = Breakdown(D(value), D("0"), D("0"), D(value))
    assert format_breakdown(b) == f"{expected} price = {expected}"
