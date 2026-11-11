"""The work-hour markup counts the hours of a leg in the local time of its departure (#2358, epic #2331): the start
and the end of a leg both use its departure offset."""

import copy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app import tokens
from app.ranking import Weights
from app.risk import work_hour_extras
from tests.test_trip_booked import trip  # noqa: F401 (fixture)
from tests.test_trip_page import ingest, offer


def _leg(depart, arrive, depart_offset_min, arrive_offset_min):
    return SimpleNamespace(depart_at=depart, arrive_at=arrive,
                           depart_offset_min=depart_offset_min, arrive_offset_min=arrive_offset_min)


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def _w():
    return Weights(hour_markup=Decimal("15"), work_hour_markup=Decimal("30"))


def _utc(day, hour, minute=0):
    return datetime(2026, 12, day, hour, minute, tzinfo=timezone.utc)


def test_the_departure_offset_gives_the_local_hours_of_a_timezone_crossing_leg():
    # Friday 14:00 local (+60) to 16:00 local (0 at the arrival): 2 work hours from 14:00 to 16:00 (#2358)
    leg = _leg(_utc(18, 13), _utc(18, 15), depart_offset_min=60, arrive_offset_min=0)
    assert work_hour_extras(_it(leg), _w()) == (("work hours", Decimal("30.00")),)


def test_a_leg_over_two_workdays_counts_the_hours_of_each_day():
    # Thursday 10:00 to Friday 12:00 local (+60 both): 7 hours on Thursday and 3 on Friday
    leg = _leg(_utc(17, 9), _utc(18, 11), depart_offset_min=60, arrive_offset_min=60)
    assert work_hour_extras(_it(leg), _w()) == (("work hours", Decimal("150.00")),)


def test_the_trip_page_shows_the_time_and_the_work_hours_of_a_friday_train(trip, sessions):  # noqa: F811
    client, trip_id = trip
    with sessions() as s:
        token = tokens.create(s, "offsets")
    o = copy.deepcopy(offer("89.90"))
    o["legs"] = [o["legs"][0]]
    o["legs"][0]["depart_at"] = "2026-12-18T14:00:00+01:00"
    o["legs"][0]["arrive_at"] = "2026-12-18T19:00:00+01:00"
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [o])
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "15", "work_hour_markup": "30"}).text
    assert "€89.90 price + €75 time + €45 work hours = €209.90" in page
