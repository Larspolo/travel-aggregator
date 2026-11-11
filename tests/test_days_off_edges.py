"""The local date of a day off and the edges of a span of days off (#2411, epic #2369).

The work-hour markup uses the departure offset of a leg for its local date (#2358). These tests use an offset that
differs from UTC, so that a wrong date (UTC instead of local) changes the result.
"""

import copy
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import DayOff, Itinerary
from app.ranking import Weights
from app.risk import work_hour_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

PASSWORD = "pw"


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


# --- the local date of a leg with a day off ---------------------------------------------------------------------


def test_a_leg_on_a_day_off_in_local_time_is_no_workday_even_when_utc_is_the_day_before(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # 09:00 to 12:00 at +10:00 is 23:00 to 02:00 UTC: the UTC date is 2026-12-23, the local date is 2026-12-24.
    _ingest_leg(client, auth, trip_id, "2026-12-24T09:00:00+10:00", "2026-12-24T12:00:00+10:00")
    _add_days_off(sessions, (date(2026, 12, 24), date(2026, 12, 24)))
    assert _work_hours(sessions, trip_id) == ()


def test_the_utc_date_of_a_leg_does_not_make_its_day_off(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_leg(client, auth, trip_id, "2026-12-24T09:00:00+10:00", "2026-12-24T12:00:00+10:00")
    _add_days_off(sessions, (date(2026, 12, 23), date(2026, 12, 23)))
    assert _work_hours(sessions, trip_id) == (("work hours", Decimal("45.00")),)


# --- the edges of a span of days off -------------------------------------------------------------------------


def test_the_day_after_a_span_of_days_off_is_a_workday(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # Thursday 2026-12-31 10:00 to 13:00: the span ends on Wednesday 2026-12-30.
    _ingest_leg(client, auth, trip_id, "2026-12-31T10:00:00+01:00", "2026-12-31T13:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 28), date(2026, 12, 30)))
    assert _work_hours(sessions, trip_id) == (("work hours", Decimal("45.00")),)


def test_the_day_before_a_span_of_days_off_is_a_workday(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # Wednesday 2026-12-23 10:00 to 13:00: the span starts on Thursday 2026-12-24.
    _ingest_leg(client, auth, trip_id, "2026-12-23T10:00:00+01:00", "2026-12-23T13:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 24), date(2026, 12, 30)))
    assert _work_hours(sessions, trip_id) == (("work hours", Decimal("45.00")),)


def test_the_workday_example_shows_work_hours_on_the_trip_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_leg(client, auth, trip_id, "2026-12-23T10:00:00+01:00", "2026-12-23T13:00:00+01:00")
    _add_days_off(sessions, (date(2026, 12, 24), date(2026, 12, 24)))
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "15", "work_hour_markup": "30"}).text
    assert "work hours" in page and "€45" in page


# --- the days-off page: a span can be deleted ---------------------------------------------------------------


def _token(c, path="/days-off"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client_login(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _save(c, first="2026-12-24", last="", note="", id=""):
    return c.post("/days-off", data={"id": id, "first_day": first, "last_day": last, "note": note,
                                     "csrf_token": _token(c)})


def test_a_span_of_days_off_can_be_deleted(client_login, sessions):
    c = client_login
    assert _save(c, "2026-12-28", "2026-12-31").status_code == 200
    with sessions() as s:
        row_id = s.scalars(select(DayOff.id)).one()
    r = c.post(f"/days-off/{row_id}/delete", data={"csrf_token": _token(c)})
    assert r.status_code in (200, 303)
    with sessions() as s:
        assert s.scalars(select(DayOff)).all() == []
    assert "No days off." in c.get("/days-off").text
