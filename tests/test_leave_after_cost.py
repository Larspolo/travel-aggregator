"""The wait before the "leave after" time of the trip in the effective cost (#2022)."""

from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.timeofday import leave_after_extras

W20 = Weights(leave_hour_markup=Decimal("20"))


def _it(depart_utc, offset_min=60):
    leg = SimpleNamespace(depart_at=depart_utc, depart_offset_min=offset_min)
    return SimpleNamespace(legs=[leg])


def test_an_early_departure_costs_the_wait():
    it = _it(datetime(2026, 12, 20, 13, 30, tzinfo=timezone.utc))  # 14:30+01:00
    assert leave_after_extras(it, time(17, 0), W20) == (("leave 2 h 30 min before 17:00", Decimal("50.00")),)


def test_no_part_at_or_after_the_time_with_no_time_or_with_0():
    at_five = datetime(2026, 12, 20, 16, 0, tzinfo=timezone.utc)  # 17:00+01:00
    late = datetime(2026, 12, 20, 17, 10, tzinfo=timezone.utc)  # 18:10+01:00
    early = datetime(2026, 12, 20, 13, 30, tzinfo=timezone.utc)  # 14:30+01:00
    assert leave_after_extras(_it(at_five), time(17, 0), W20) == ()
    assert leave_after_extras(_it(late), time(17, 0), W20) == ()
    assert leave_after_extras(_it(early), None, W20) == ()
    assert leave_after_extras(_it(early), time(17, 0), Weights()) == ()


def test_no_part_with_no_legs():
    assert leave_after_extras(SimpleNamespace(legs=[]), time(17, 0), W20) == ()
