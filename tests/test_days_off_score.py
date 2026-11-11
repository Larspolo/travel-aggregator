"""The days off count as weekend days in the work-hour markup (#2371, epic #2331)."""

import copy
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import DayOff, Itinerary
from app.ranking import Weights
from app.risk import work_hour_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _weights():
    return Weights(hour_markup=Decimal("15"), work_hour_markup=Decimal("30"))


def _add_days_off(sessions, *spans):
    with sessions() as s:
        for first, last in spans:
            s.add(DayOff(first_day=first, last_day=last, note="", updated_at=datetime.now(timezone.utc)))
        s.commit()


def _ingest_leg(client, auth, trip_id, depart, arrive, price="89.90"):
    o = copy.deepcopy(offer(price))
    o["legs"] = [dict(o["legs"][0], depart_at=depart, arrive_at=arrive)]
    ingest(client, auth, trip_id, [o])


def _work_hours(sessions, trip_id):
    with sessions() as s:
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).one()
        return work_hour_extras(it, _weights())


def test_a_train_on_a_day_off_costs_the_hour_markup_only(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_leg(client, auth, trip_id, "2026-12-24T10:00:00+01:00", "2026-12-24T13:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 24), date(2026, 12, 24)))
    assert _work_hours(sessions, trip_id) == ()
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "15", "work_hour_markup": "30"}).text
    assert "€89.90 price + €45 time = €134.90" in page


def test_the_same_train_on_a_workday_costs_the_work_hours(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_leg(client, auth, trip_id, "2026-12-23T10:00:00+01:00", "2026-12-23T13:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 24), date(2026, 12, 24)))
    assert _work_hours(sessions, trip_id) == (("work hours", Decimal("45.00")),)


def test_a_leg_over_a_day_off_counts_no_work_hours_on_that_day(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # Wednesday 08:00 to Thursday 12:00 local. Work hours 9:00 to 17:00: only Wednesday's 8 hours count (day off: Thursday).
    _ingest_leg(client, auth, trip_id, "2026-12-23T08:00:00+01:00", "2026-12-24T12:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 24), date(2026, 12, 24)))
    assert _work_hours(sessions, trip_id) == (("work hours", Decimal("120.00")),)


def test_a_span_of_days_off_makes_each_of_its_days_a_day_off(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # Monday 28 to Thursday 31 December: four workdays, all days off
    _ingest_leg(client, auth, trip_id, "2026-12-28T08:00:00+01:00", "2026-12-31T18:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 28), date(2026, 12, 31)))
    assert _work_hours(sessions, trip_id) == ()


def test_no_days_off_keeps_the_work_hours_of_the_span(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_leg(client, auth, trip_id, "2026-12-28T08:00:00+01:00", "2026-12-31T18:00:00+01:00")
    assert _work_hours(sessions, trip_id) == (("work hours", Decimal("480.00")),)
