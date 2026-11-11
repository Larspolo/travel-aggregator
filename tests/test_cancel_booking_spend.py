"""The summary per year counts the paid price less the refund of a cancelled booking, and no journey (#1687)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.spend import year_summary

UTC = timezone.utc
EUR_ONLY: dict[str, Decimal] = {}


def _leg(mode, depart, minutes):
    return SimpleNamespace(mode=mode, depart_at=depart, arrive_at=depart + timedelta(minutes=minutes),
                           depart_offset_min=0)


def _journey(price, currency="EUR", refund=None, cancelled=False, mode="train", minutes=600):
    depart = datetime(2026, 5, 1, 9, tzinfo=UTC)
    legs = [_leg(mode, depart, minutes)]
    return SimpleNamespace(legs=legs, depart_at=depart, duration_min=minutes, booked_price=Decimal(price),
                           booked_currency=currency, refund_price=None if refund is None else Decimal(refund),
                           cancelled_at=depart if cancelled else None)


def test_a_cancelled_booking_counts_the_paid_price_less_the_refund_and_no_journey():
    (year,) = year_summary([_journey("89.00", refund="60.00", cancelled=True)], EUR_ONLY)
    assert year.year == 2026
    assert year.paid_eur == Decimal("29.00")
    assert year.journeys == 0
    assert year.hours == 0
    assert year.co2_kg == 0
    (line,) = year.modes
    assert (line.mode, line.journeys, line.paid_eur, line.hours) == ("train", 0, Decimal("29.00"), 0)


def test_a_cancelled_booking_with_no_refund_counts_the_full_paid_price():
    (year,) = year_summary([_journey("89.00", cancelled=True)], EUR_ONLY)
    assert year.paid_eur == Decimal("89.00")
    assert year.journeys == 0


def test_a_booked_journey_that_is_not_cancelled_counts_as_before():
    (year,) = year_summary([_journey("89.00", refund="60.00")], EUR_ONLY)
    assert year.paid_eur == Decimal("89.00")
    assert year.journeys == 1
    assert year.hours == 10


def test_a_refund_in_another_currency_uses_the_rate_of_that_currency():
    rates = {"USD": Decimal("0.90")}
    (year,) = year_summary([_journey("100.00", currency="USD", refund="50.00", cancelled=True)], rates)
    assert year.paid_eur == Decimal("45.00")
    assert year.missing == {}
