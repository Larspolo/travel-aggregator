"""The work-hour markup (#2332): each hour of a leg on a local workday between the work-hour start and end costs
(value − hour_markup)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import work_hour_extras


def _leg(depart, arrive, offset_min=60):
    return SimpleNamespace(depart_at=depart, arrive_at=arrive, depart_offset_min=offset_min, arrive_offset_min=offset_min)


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def _w(work=Decimal("30"), hour=Decimal("15")):
    return Weights(hour_markup=hour, work_hour_markup=work)


def _utc(day, hour):
    # local time = UTC + 1 h (offset +60)
    return datetime(2026, 12, day, hour, tzinfo=timezone.utc) - timedelta(hours=1)


def test_friday_afternoon_leg_gives_three_work_hours_at_fifteen_difference():
    leg = _leg(_utc(18, 14), _utc(18, 19))
    assert work_hour_extras(_it(leg), _w()) == (("work hours", Decimal("45.00")),)


def test_the_same_leg_on_saturday_adds_no_part():
    leg = _leg(_utc(19, 14), _utc(19, 19))
    assert work_hour_extras(_it(leg), _w()) == ()


def test_no_value_adds_no_part():
    leg = _leg(_utc(18, 14), _utc(18, 19))
    assert work_hour_extras(_it(leg), Weights(hour_markup=Decimal("15"))) == ()


def test_a_value_equal_to_the_hour_markup_adds_no_part():
    leg = _leg(_utc(18, 14), _utc(18, 19))
    assert work_hour_extras(_it(leg), _w(work=Decimal("15"))) == ()


def test_a_thursday_evening_to_friday_morning_leg_counts_two_work_hours():
    leg = _leg(_utc(17, 16), _utc(18, 10))
    assert work_hour_extras(_it(leg), _w()) == (("work hours", Decimal("30.00")),)


def test_the_work_hour_window_follows_the_settings():
    leg = _leg(_utc(18, 14), _utc(18, 19))
    w = Weights(hour_markup=Decimal("15"), work_hour_markup=Decimal("30"), work_hour_start=15, work_hour_end=16)
    assert work_hour_extras(_it(leg), w) == (("work hours", Decimal("15.00")),)


def test_the_value_survives_a_profile_config():
    from app.profiles import from_config, to_config

    w = Weights(work_hour_markup=Decimal("30"), work_hour_start=8, work_hour_end=18)
    assert from_config(to_config(w)) == w
