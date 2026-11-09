"""The CO₂ of the booked journeys per year and per mode (#1464): plain objects, no database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.spend import year_summary

UTC = timezone.utc
WEIGHTS = Weights(co2_flight_kg_h=Decimal("90"), co2_train_kg_h=Decimal("3"))


def _leg(mode, depart, hours):
    return SimpleNamespace(mode=mode, depart_at=depart, arrive_at=depart + timedelta(hours=hours),
                           depart_offset_min=0)


def _journey(legs, minutes=60, price=None, currency=None):
    return SimpleNamespace(legs=legs, depart_at=legs[0].depart_at if legs else datetime(2026, 1, 1, tzinfo=UTC),
                           duration_min=minutes, booked_price=price, booked_currency=currency)


def _at(*args):
    return datetime(*args, tzinfo=UTC)


def test_a_flight_and_a_train_give_the_kg_of_the_year_and_of_each_line():
    flight = _journey([_leg("flight", _at(2026, 3, 1, 8), 2)], 120)
    train = _journey([_leg("train", _at(2026, 4, 1, 8), 4)], 240)
    (year,) = year_summary([flight, train], {}, WEIGHTS)
    assert year.co2_kg == Decimal("192")
    lines = {line.mode: line.co2_kg for line in year.modes}
    assert lines == {"flight": Decimal("180"), "train": Decimal("12")}


def test_a_journey_with_no_legs_adds_zero_kg():
    empty = _journey([], 0)
    (year,) = year_summary([empty], {}, WEIGHTS)
    assert year.co2_kg == Decimal("0")


def test_a_train_and_bus_journey_adds_the_kg_of_both_legs_to_the_train_line():
    journey = _journey([_leg("train", _at(2026, 5, 1, 8), 2), _leg("bus", _at(2026, 5, 1, 10), 1)], 180)
    (year,) = year_summary([journey], {}, WEIGHTS)
    # train 2 h * 3 kg + bus 1 h * 2 kg (default weights) = 8 kg
    assert year.co2_kg == Decimal("8")
    assert [(line.mode, line.co2_kg) for line in year.modes] == [("train", Decimal("8"))]


def test_the_kg_are_rounded_half_up_only_at_the_end():
    # Three journeys of 0.5 kg each: 1.5 kg in all, rounded once to 2 kg (per journey it would be 3 kg).
    def half_hour_train(day):
        return _journey([SimpleNamespace(mode="train", depart_at=_at(2026, 6, day, 8),
                                         arrive_at=_at(2026, 6, day, 8, 30), depart_offset_min=0)], 30)
    journeys = [half_hour_train(day) for day in (1, 2, 3)]
    (year,) = year_summary(journeys, {}, Weights(co2_train_kg_h=Decimal("1")))
    assert year.co2_kg == Decimal("2")
    assert year.modes[0].co2_kg == Decimal("2")
