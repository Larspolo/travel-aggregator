"""The score part of each mode with an hour value (#1594): bus, flight and ferry parts, and a wait between two legs
adds no mode part (#1566, criteria 3 and 4)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import mode_hour_extras

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


def leg(mode, hours, start_min=0):
    depart = T0 + timedelta(minutes=start_min)
    return SimpleNamespace(mode=mode, depart_at=depart, arrive_at=depart + timedelta(hours=hours),
                           from_name="A", to_name="B", carrier="")


def _it(*legs):
    return SimpleNamespace(legs=list(legs), mode_summary="+".join(dict.fromkeys(lg.mode for lg in legs)))


def test_a_bus_leg_of_three_hours_at_value_twenty_five_with_hour_markup_fifteen_costs_thirty():
    w = Weights(hour_markup=Decimal("15"), bus_hour_markup=Decimal("25"))
    assert mode_hour_extras(_it(leg("bus", 3)), w) == (("bus hours", Decimal("30")),)


def test_a_flight_leg_of_two_hours_at_value_thirty_with_hour_markup_fifteen_costs_thirty():
    w = Weights(hour_markup=Decimal("15"), flight_hour_markup=Decimal("30"))
    assert mode_hour_extras(_it(leg("flight", 2)), w) == (("flight hours", Decimal("30")),)


def test_a_ferry_leg_of_five_hours_at_value_nine_with_hour_markup_fifteen_gives_minus_thirty():
    w = Weights(hour_markup=Decimal("15"), ferry_hour_markup=Decimal("9"))
    assert mode_hour_extras(_it(leg("ferry", 5)), w) == (("ferry hours", Decimal("-30")),)


def test_a_wait_between_two_train_legs_adds_no_part():
    w = Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("5"))
    it = _it(leg("train", 2), leg("train", 2, 180))  # 1 h wait between the legs
    assert mode_hour_extras(it, w) == (("train hours", Decimal("-40")),)


def test_all_four_values_give_one_part_per_mode_in_the_order_of_hour_fields():
    w = Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("5"), bus_hour_markup=Decimal("25"),
                flight_hour_markup=Decimal("30"), ferry_hour_markup=Decimal("9"))
    it = _it(leg("train", 1), leg("bus", 1, 60))
    assert mode_hour_extras(it, w) == (("train hours", Decimal("-10")), ("bus hours", Decimal("10")))
