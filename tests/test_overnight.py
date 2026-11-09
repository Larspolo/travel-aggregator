"""The overnight stop cost (#1256)."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost
from app.timeofday import overnight_extras

UTC = timezone.utc
W = Weights(overnight_cost=Decimal("80"), overnight_min=240)


def _leg(dep, arr, to="Köln", off=60):
    return SimpleNamespace(depart_at=dep, depart_offset_min=off, arrive_at=arr, arrive_offset_min=off, to_name=to)


def _at(day, h, m=0):
    return datetime(2026, 12, day, h, m, tzinfo=UTC)


def test_night_transfer_in_koeln_adds_the_cost():
    # Local +01:00: arrive 23:40, depart 06:10.
    it = SimpleNamespace(legs=[_leg(_at(20, 19), _at(20, 22, 40)), _leg(_at(21, 5, 10), _at(21, 9), to="Wien")])
    extras = overnight_extras(it, W)
    assert extras == (("overnight stop in Köln", Decimal("80")),)
    assert (effective_cost(Decimal("100"), 0, 0, W, extras).total
            - effective_cost(Decimal("100"), 0, 0, W, ()).total) == Decimal("80")


def test_short_transfer_no_transfer_and_direct_night_train_give_no_line():
    short = SimpleNamespace(legs=[_leg(_at(20, 19), _at(20, 22, 50)), _leg(_at(20, 23, 20), _at(21, 2))])
    assert overnight_extras(short, W) == ()
    assert overnight_extras(SimpleNamespace(legs=[]), W) == ()
    assert overnight_extras(SimpleNamespace(legs=[_leg(_at(20, 21), _at(21, 7))]), W) == ()


def test_zero_cost_gives_no_line():
    it = SimpleNamespace(legs=[_leg(_at(20, 19), _at(20, 22, 40)), _leg(_at(21, 5, 10), _at(21, 9))])
    assert overnight_extras(it, Weights()) == ()
