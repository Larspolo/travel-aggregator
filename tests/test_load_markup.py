"""The markup of the expected load per leg (#2608, epic #2607): level 2 adds the high markup; levels 3 and 4 add
the very high markup; level 1 and a markup of 0 add nothing."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import load_extras

T0 = datetime(2026, 12, 18, 9, 0, tzinfo=timezone.utc)


def _leg(first=None, second=None):
    return SimpleNamespace(depart_at=T0, arrive_at=T0, load_first=first, load_second=second)


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def _fare(travel_class="standard"):
    return SimpleNamespace(travel_class=travel_class)


def _w(high=Decimal("3"), very_high=Decimal("8")):
    return Weights(load_high_markup=high, load_very_high_markup=very_high)


def test_a_very_high_second_class_leg_adds_the_very_high_markup():
    it = _it(_leg(second=3), _leg(second=1))
    assert load_extras(_fare(), it, _w()) == (("expected load very high", Decimal("8")),)


def test_high_and_fully_booked_legs_give_one_part_each_with_the_sum():
    it = _it(_leg(second=2), _leg(second=2), _leg(second=4))
    assert load_extras(_fare(), it, _w()) == (
        ("expected load high", Decimal("6")), ("expected load fully booked", Decimal("8")))


def test_a_first_fare_uses_the_first_class_load_only():
    it = _it(_leg(first=None, second=3))
    assert load_extras(_fare("first"), it, _w()) == ()
    assert load_extras(_fare("first"), _it(_leg(first=2, second=4)), _w()) == (("expected load high", Decimal("3")),)


def test_a_fare_without_travel_class_uses_the_second_class_load():
    assert load_extras(_fare(None), _it(_leg(first=4, second=2)), _w()) == (("expected load high", Decimal("3")),)


def test_a_markup_of_zero_or_no_level_gives_no_part():
    it = _it(_leg(second=3), _leg(second=4))
    assert load_extras(_fare(), it, _w(very_high=Decimal("0"))) == ()
    assert load_extras(_fare(), _it(_leg(second=None)), _w()) == ()
    assert load_extras(_fare(), _it(_leg(second=1)), _w()) == ()
