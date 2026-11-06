from decimal import Decimal
from pathlib import Path

import pytest

from app.ranking import Breakdown, Weights, effective_cost


def test_example_of_ticket():
    result = effective_cost(Decimal("90"), 248, 2, Weights(Decimal("15"), Decimal("10")))
    assert result == Breakdown(Decimal("90.00"), Decimal("62.00"), Decimal("20.00"), Decimal("172.00"))


def test_defaults():
    assert Weights() == Weights(Decimal("15"), Decimal("10"))


@pytest.mark.parametrize("price,minutes,transfers", [("19.995", 7, 0), ("0", 1, 3), ("33.333", 59, 1)])
def test_total_is_sum_of_parts(price, minutes, transfers):
    r = effective_cost(Decimal(price), minutes, transfers, Weights())
    assert r.total == r.price + r.time_cost + r.transfer_cost
    for part in (r.price, r.time_cost, r.transfer_cost, r.total):
        assert part.as_tuple().exponent == -2


def test_half_even_rounding():
    # 1 minute at 0.3/h = 0.005 -> 0.00 (half even)
    r = effective_cost(Decimal("0.125"), 1, 0, Weights(Decimal("0.3"), Decimal("0")))
    assert r.price == Decimal("0.12")
    assert r.time_cost == Decimal("0.00")


@pytest.mark.parametrize(
    "args",
    [
        (Decimal("-1"), 10, 0, Weights()),
        (Decimal("1"), -10, 0, Weights()),
        (Decimal("1"), 10, -1, Weights()),
        (Decimal("1"), 10, 0, Weights(Decimal("-1"), Decimal("10"))),
        (Decimal("1"), 10, 0, Weights(Decimal("15"), Decimal("-1"))),
    ],
)
def test_negative_input_raises(args):
    with pytest.raises(ValueError):
        effective_cost(*args)


def test_no_float_in_module():
    source = (Path(__file__).parent.parent / "app" / "ranking.py").read_text()
    assert "float" not in source
