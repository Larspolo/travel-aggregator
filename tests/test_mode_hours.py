"""The hour value per mode (#1567): the minutes of each leg cost the hour value of its mode, and the airport time
of a flight uses the flight hour value."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.door import door_extras, flight_extras
from app.profiles import from_config, to_config
from app.ranking import Weights
from app.risk import mode_hour_extras
from app.web.pages import row_cost

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


def leg(mode, hours, start_min=0):
    depart = T0 + timedelta(minutes=start_min)
    return SimpleNamespace(mode=mode, depart_at=depart, arrive_at=depart + timedelta(hours=hours),
                           from_name="A", to_name="B", carrier="")


def _it(*legs):
    return SimpleNamespace(legs=list(legs), mode_summary="+".join(dict.fromkeys(lg.mode for lg in legs)))


def test_train_hours_of_four_hours_at_value_five_with_hour_markup_fifteen_cost_minus_forty():
    w = Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("5"))
    it = _it(leg("train", 4), leg("bus", 2, 300))
    assert mode_hour_extras(it, w) == (("train hours", Decimal("-40")),)


def test_a_mode_without_a_value_adds_no_part():
    w = Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("5"))
    assert mode_hour_extras(_it(leg("bus", 2)), w) == ()


def test_a_value_equal_to_the_hour_markup_adds_no_part():
    w = Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("15"))
    assert mode_hour_extras(_it(leg("train", 4)), w) == ()


def test_a_walk_leg_adds_nothing_even_with_all_values_set():
    w = Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("5"), bus_hour_markup=Decimal("5"),
                flight_hour_markup=Decimal("30"), ferry_hour_markup=Decimal("5"))
    assert mode_hour_extras(_it(leg("walk", 1)), w) == ()


def test_a_value_equal_to_the_hour_markup_gives_the_same_row_cost_as_none():
    fare = SimpleNamespace(id=1, latest_price=Decimal("50.00"), currency="EUR", flexibility=None, travel_class=None,
                           self_transfers=0, checked_bags_included=0, checked_bag_price=None, source="test",
                           latest_captured_at=T0, seen_price=None, name="f", default=False)
    it = SimpleNamespace(legs=[leg("train", 4), leg("bus", 1, 300)], duration_min=300, transfers=1,
                         mode_summary="train+bus", trip=SimpleNamespace(travelers=1, arrive_by=None))
    unset = row_cost(it, [fare], [], Weights(), T0)[1].total
    same = row_cost(it, [fare], [], Weights(train_hour_markup=Decimal("15"), bus_hour_markup=Decimal("15")), T0)
    assert unset == same[1].total


def test_a_flight_uses_the_flight_hour_value_for_the_airport_time():
    it = _it(leg("flight", 2))
    w = Weights(hour_markup=Decimal("15"), flight_hour_markup=Decimal("30"))
    assert flight_extras(it, w) == (("airport time", Decimal("75")),)


def test_a_flight_without_a_flight_value_keeps_the_hour_markup_for_the_airport_time():
    it = _it(leg("flight", 2))
    assert flight_extras(it, Weights(hour_markup=Decimal("15"))) == (("airport time", Decimal("37.5")),)


def test_a_door_place_keeps_the_hour_markup():
    it = _it(leg("flight", 2))
    place = SimpleNamespace(id=1, kind="access", place_text="A", minutes=60, cost=Decimal("0"))
    assert door_extras(it, [place], Weights(hour_markup=Decimal("15")).hour_markup) == (
        ("access time", Decimal("15")), ("access cost", Decimal("0")))


def test_to_config_and_from_config_keep_a_value_and_none():
    w = Weights(train_hour_markup=Decimal("5"), bus_hour_markup=None)
    back = from_config(to_config(w))
    assert back.train_hour_markup == Decimal("5")
    assert back.bus_hour_markup is None
    assert back.flight_hour_markup is None


def test_a_train_value_of_five_lowers_the_row_cost_by_forty():
    fare = SimpleNamespace(id=1, latest_price=Decimal("50.00"), currency="EUR", flexibility=None, travel_class=None,
                           self_transfers=0, checked_bags_included=0, checked_bag_price=None, source="test",
                           latest_captured_at=T0, seen_price=None, name="f", default=False)
    it = SimpleNamespace(legs=[leg("train", 4), leg("bus", 1, 300)], duration_min=300, transfers=1,
                         mode_summary="train+bus", trip=SimpleNamespace(travelers=1, arrive_by=None))
    unset = row_cost(it, [fare], [], Weights(hour_markup=Decimal("15")), T0)[1].total
    cheap = row_cost(it, [fare], [], Weights(hour_markup=Decimal("15"), train_hour_markup=Decimal("5")), T0)
    assert cheap[1].total == unset - Decimal("40")
