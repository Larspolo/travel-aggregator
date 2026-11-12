"""The work-seat hour value (#2566, epic #2565): each hour of a leg with both Wi-Fi and power sockets costs
(value − hour_markup); a leg with one service, or none, adds no part."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import work_seat_extras

T0 = datetime(2026, 12, 18, 9, 0, tzinfo=timezone.utc)


def _leg(hours, services):
    return SimpleNamespace(depart_at=T0, arrive_at=T0.replace(hour=9 + hours), services=services)


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def _w(seat=Decimal("5"), hour=Decimal("15")):
    return Weights(hour_markup=hour, work_seat_hour_markup=seat)


def test_a_four_hour_leg_with_wifi_and_power_gives_minus_forty():
    assert work_seat_extras(_it(_leg(4, "wifi,power")), _w()) == (("work seat", Decimal("-40.00")),)


def test_a_leg_with_one_service_or_none_gives_no_part():
    for services in (None, "wifi", "power"):
        assert work_seat_extras(_it(_leg(4, services)), _w()) == (), services


def test_no_value_gives_no_part():
    assert work_seat_extras(_it(_leg(4, "wifi,power")), _w(seat=None)) == ()


def test_a_value_equal_to_the_hour_markup_gives_no_part():
    assert work_seat_extras(_it(_leg(4, "wifi,power")), _w(seat=Decimal("15"))) == ()


def test_two_legs_count_only_the_leg_with_both_services():
    it = _it(_leg(2, "wifi,power"), _leg(1, None))
    assert work_seat_extras(it, _w()) == (("work seat", Decimal("-20.00")),)
