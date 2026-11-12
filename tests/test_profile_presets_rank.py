"""A profile from a "Start from" preset ranks the offers as its weights say (#2521)."""

from decimal import Decimal

import pytest

from app.profiles import preset_weights
from app.ranking import effective_cost

# (name, price, duration in minutes, transfers): a bus of 8 h with no transfer, a train of 5 h with one transfer
BUS = ("bus", Decimal("25"), 8 * 60, 0)
TRAIN = ("train", Decimal("65"), 5 * 60, 1)


@pytest.mark.parametrize(("preset", "bus_total", "train_total", "first"),
                         [("budget", "65.00", "95.00", "bus"),
                          ("balanced", "145.00", "150.00", "bus"),
                          ("time", "345.00", "290.00", "train")])
def test_a_preset_gives_the_totals_and_the_order_of_its_name(preset, bus_total, train_total, first):
    weights = preset_weights(preset)
    bus = effective_cost(BUS[1], BUS[2], BUS[3], weights).total
    train = effective_cost(TRAIN[1], TRAIN[2], TRAIN[3], weights).total
    assert bus == Decimal(bus_total) and train == Decimal(train_total)
    ranked = sorted([(bus, BUS[0]), (train, TRAIN[0])])
    assert ranked[0][1] == first
