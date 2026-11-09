"""The CO₂ part of an offer: kg per hour of each leg and a price per kg (#1416)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.co2 import co2_extras, co2_kg
from app.ranking import Weights, effective_cost

UTC = timezone.utc
PRICED = Weights(co2_price_kg=Decimal("0.10"))


def _leg(mode, minutes):
    dep = datetime(2026, 12, 20, 8, 0, tzinfo=UTC)
    return SimpleNamespace(mode=mode, depart_at=dep, arrive_at=dep + timedelta(minutes=minutes))


def test_flight_leg_of_two_hours_gives_the_part():
    it = SimpleNamespace(legs=[_leg("flight", 120)])
    assert co2_kg(it, PRICED) == Decimal("180")
    assert co2_extras(it, PRICED) == (("CO₂ 180 kg", Decimal("18.00")),)


def test_train_and_bus_legs_add_up():
    it = SimpleNamespace(legs=[_leg("train", 120), _leg("bus", 90)])
    assert co2_kg(it, Weights()) == Decimal("9")
    assert co2_extras(it, PRICED) == (("CO₂ 9 kg", Decimal("0.90")),)


def test_other_mode_adds_nothing():
    it = SimpleNamespace(legs=[_leg("walk", 180)])
    assert co2_kg(it, PRICED) == Decimal("0")
    assert co2_extras(it, PRICED) == ()


def test_zero_price_gives_no_line_and_no_cost():
    it = SimpleNamespace(legs=[_leg("flight", 120)])
    assert co2_extras(it, Weights()) == ()
    assert effective_cost(Decimal("100"), 0, 0, Weights(), co2_extras(it, Weights())).total == (
        effective_cost(Decimal("100"), 0, 0, Weights(), ()).total
    )


def test_flight_part_adds_eighteen_euros_to_the_total():
    it = SimpleNamespace(legs=[_leg("flight", 120)])
    extras = co2_extras(it, PRICED)
    assert (effective_cost(Decimal("100"), 0, 0, PRICED, extras).total
            - effective_cost(Decimal("100"), 0, 0, PRICED, ()).total) == Decimal("18.00")
