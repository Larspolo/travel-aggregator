"""The booked journeys per year and per mode (#1363): plain objects, no database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.spend import year_summary

UTC = timezone.utc


def _leg(mode, depart, minutes, offset=0):
    return SimpleNamespace(mode=mode, depart_at=depart, arrive_at=depart + timedelta(minutes=minutes),
                           depart_offset_min=offset)


def _journey(legs, minutes, price=None, currency=None, depart=None):
    return SimpleNamespace(legs=legs, depart_at=depart or legs[0].depart_at, duration_min=minutes,
                           booked_price=price, booked_currency=currency, cancelled_at=None, refund_price=None)


def _at(*args):
    return datetime(*args, tzinfo=UTC)


def test_seven_journeys_of_2026_sum_to_the_paid_total_and_the_hours():
    prices = ["90.00", "90.00", "90.00", "100.00", "100.00", "100.00", "72.50"]
    modes = ["train"] * 3 + ["bus"] * 2 + ["flight"] * 2
    itineraries = [
        _journey([_leg(mode, _at(2026, 3, i + 1, 9), 500)], 500 if i < 6 else 660, Decimal(price))
        for i, (mode, price) in enumerate(zip(modes, prices))
    ]
    (year,) = year_summary(itineraries, {})
    assert year.year == 2026
    assert year.journeys == 7
    assert year.paid_eur == Decimal("642.50")
    assert year.hours == 61
    assert sorted(line.mode for line in year.modes) == ["bus", "flight", "train"]


def test_the_year_is_the_local_year_of_the_first_leg():
    late_utc = _journey([_leg("train", _at(2026, 12, 31, 22, 30), 60, offset=60)], 60)
    early_local = _journey([_leg("train", _at(2026, 12, 31, 23, 30), 60, offset=60)], 60)
    years = {y.year: y.journeys for y in year_summary([late_utc, early_local], {})}
    assert years == {2026: 1, 2027: 1}


def test_a_train_and_bus_journey_counts_as_train():
    journey = _journey([_leg("train", _at(2026, 5, 1, 8), 120), _leg("bus", _at(2026, 5, 1, 10), 30)], 150)
    (year,) = year_summary([journey], {})
    assert [(line.mode, line.journeys) for line in year.modes] == [("train", 1)]


def test_a_paid_price_with_no_rate_is_missing_and_not_summed():
    chf = _journey([_leg("train", _at(2026, 6, 1, 8), 90)], 90, Decimal("50.00"), "CHF")
    unpaid = _journey([_leg("train", _at(2026, 6, 2, 8), 90)], 90)
    (year,) = year_summary([chf, unpaid], {})
    assert year.journeys == 2
    assert year.paid_eur is None
    assert year.missing == {"CHF": 1}
    assert year.hours == 3


def test_a_rate_converts_a_foreign_price_to_eur():
    usd = _journey([_leg("flight", _at(2026, 7, 1, 8), 60)], 60, Decimal("100.00"), "USD")
    (year,) = year_summary([usd], {"USD": Decimal("0.90")})
    assert year.paid_eur == Decimal("90.00")
    assert year.missing == {}


def test_years_are_newest_first_and_hours_round_half_up():
    old = _journey([_leg("bus", _at(2025, 1, 1, 8), 30)], 30)
    new = _journey([_leg("bus", _at(2026, 1, 1, 8), 90)], 90)
    years = year_summary([old, new], {})
    assert [y.year for y in years] == [2026, 2025]
    assert years[0].hours == 2  # 90 min is 1.5 h, rounded half up
    assert years[1].hours == 1  # 30 min is 0.5 h, rounded half up
