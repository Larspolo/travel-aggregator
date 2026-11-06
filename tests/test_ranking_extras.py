from decimal import Decimal

import pytest

from app.ranking import Breakdown, Weights, effective_cost, format_breakdown


def D(value: str) -> Decimal:
    return Decimal(value)


def test_extra_is_added_to_total_and_kept():
    r = effective_cost(D("90"), 248, 2, Weights(D("15"), D("10")), extras=(("access", D("12.50")),))
    assert r.total == D("184.50")
    assert r.extras == (("access", D("12.50")),)


def test_extra_is_rounded_to_cents():
    r = effective_cost(D("0"), 0, 0, Weights(), extras=(("fee", D("1.005")),))
    assert r.extras == (("fee", D("1.00")),)
    assert r.total == D("1.00")


def test_format_prints_extra_after_transfers():
    b = Breakdown(D("90.00"), D("62.00"), D("0.00"), D("164.50"), (("access", D("12.50")),))
    assert format_breakdown(b) == "€90 price + €62 time + €12.50 access = €164.50"


def test_format_with_extra_and_transfers():
    b = Breakdown(D("90.00"), D("62.00"), D("30.00"), D("194.50"), (("access", D("12.50")),))
    assert format_breakdown(b) == "€90 price + €62 time + €30 transfers + €12.50 access = €194.50"


def test_zero_extra_is_left_out():
    b = Breakdown(D("90.00"), D("62.00"), D("30.00"), D("182.00"), (("access", D("0.00")),))
    assert format_breakdown(b) == "€90 price + €62 time + €30 transfers = €182"


def test_no_extras_output_is_unchanged():
    b = Breakdown(D("90.00"), D("62.00"), D("30.00"), D("182.00"))
    assert b.extras == ()
    assert format_breakdown(b) == "€90 price + €62 time + €30 transfers = €182"


def test_negative_extra_bonus_is_allowed():
    r = effective_cost(D("90"), 60, 0, Weights(D("15"), D("10")), extras=(("bonus", D("-5")),))
    assert r.extras == (("bonus", D("-5.00")),)
    assert r.total == D("100.00")


@pytest.mark.parametrize(
    "args",
    [
        (D("-1"), 10, 0, Weights()),
        (D("1"), -10, 0, Weights()),
        (D("1"), 10, 0, Weights(D("-1"), D("10"))),
    ],
)
def test_negative_input_still_raises_with_extras(args):
    with pytest.raises(ValueError):
        effective_cost(*args, extras=(("access", D("12.50")),))
