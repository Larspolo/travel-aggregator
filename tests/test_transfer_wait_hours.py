"""The transfer wait hour value (#2220): the time between two legs costs (value − hour_markup) per hour."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import transfer_wait_extras

D = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)


def leg(seq, depart_h, depart_m, arrive_h, arrive_m):
    return SimpleNamespace(seq=seq, mode="train", carrier="",
                           depart_at=D.replace(hour=depart_h, minute=depart_m),
                           arrive_at=D.replace(hour=arrive_h, minute=arrive_m))


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def test_a_wait_of_one_and_a_half_hours_at_value_twenty_five_with_hour_markup_fifteen_adds_fifteen():
    it = _it(leg(1, 8, 0, 10, 0), leg(2, 11, 30, 12, 30))
    w = Weights(hour_markup=Decimal("15"), transfer_wait_hour_markup=Decimal("25"))
    parts = transfer_wait_extras(it, w)
    assert parts == (("transfer wait", Decimal("15")),)
    assert round(parts[0][1], 2) == Decimal("15.00")


def test_one_leg_adds_no_part():
    w = Weights(hour_markup=Decimal("15"), transfer_wait_hour_markup=Decimal("25"))
    assert transfer_wait_extras(_it(leg(1, 8, 0, 10, 0)), w) == ()


def test_no_value_adds_no_part():
    it = _it(leg(1, 8, 0, 10, 0), leg(2, 11, 30, 12, 30))
    assert transfer_wait_extras(it, Weights(hour_markup=Decimal("15"))) == ()


def test_a_value_equal_to_the_hour_markup_adds_no_part():
    it = _it(leg(1, 8, 0, 10, 0), leg(2, 11, 30, 12, 30))
    w = Weights(hour_markup=Decimal("15"), transfer_wait_hour_markup=Decimal("15"))
    assert transfer_wait_extras(it, w) == ()


def test_a_lower_value_gives_a_discount():
    it = _it(leg(1, 8, 0, 10, 0), leg(2, 11, 30, 12, 30))
    w = Weights(hour_markup=Decimal("15"), transfer_wait_hour_markup=Decimal("5"))
    assert transfer_wait_extras(it, w) == (("transfer wait", Decimal("-15")),)


def test_an_overlap_adds_no_wait():
    it = _it(leg(1, 8, 0, 10, 0), leg(2, 9, 0, 9, 30))
    w = Weights(hour_markup=Decimal("15"), transfer_wait_hour_markup=Decimal("25"))
    assert transfer_wait_extras(it, w) == ()


def test_the_legs_are_sorted_by_seq():
    it = _it(leg(2, 11, 30, 12, 30), leg(1, 8, 0, 10, 0))
    w = Weights(hour_markup=Decimal("15"), transfer_wait_hour_markup=Decimal("25"))
    assert transfer_wait_extras(it, w) == (("transfer wait", Decimal("15")),)


def test_a_saved_profile_keeps_the_value():
    from app.profiles import from_config, to_config
    w = Weights(transfer_wait_hour_markup=Decimal("25"))
    assert from_config(to_config(w)).transfer_wait_hour_markup == Decimal("25")
    assert from_config(to_config(Weights())).transfer_wait_hour_markup is None
