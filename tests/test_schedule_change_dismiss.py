"""Dismiss hides a timetable change until the times change again (#2342)."""

import re
from datetime import timedelta

from alembic import command
from sqlalchemy import create_engine, inspect

from tests.test_schedule_change import SEEN, at, client, itinerary  # noqa: F401 (fixture)
from tests.test_trip_booked import _alembic

from app.models import Trip

MARK = "Timetable changed:"


def text(c):
    return re.sub(r"\s+", " ", c.get("/upcoming").text)


def test_dismiss_hides_until_new_times(client, sessions):  # noqa: F811
    with sessions() as s:
        trip = Trip(title="Basel", status="planning")
        trip.itineraries = [itinerary("old", at(8, 15), at(14, 28), SEEN, booked=True),
                            itinerary("new", at(8, 42), at(14, 55), SEEN + timedelta(days=1))]
        s.add(trip)
        s.commit()
        trip_id = trip.id
    html = client.get("/upcoming").text
    form = re.search(r'<form class="inline-form" method="post" action="([^"]+/schedule-change/dismiss)">(.*?)</form>',
                     html, re.S)
    fields = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', form.group(2)))
    r = client.post(form.group(1), data=fields, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/upcoming"
    assert MARK not in text(client)

    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.itineraries.append(itinerary("newer", at(9, 0), at(15, 10), SEEN + timedelta(days=2)))
        s.commit()
    assert "Timetable changed: ICE 145 now 09:00 → 15:10 (was 08:15 → 14:28)" in text(client)


def test_dismiss_needs_csrf_and_a_matching_trip(client, sessions):  # noqa: F811
    with sessions() as s:
        trip = Trip(title="Basel", status="planning")
        trip.itineraries = [itinerary("old", at(8, 15), at(14, 28), SEEN, booked=True)]
        s.add(trip)
        s.commit()
        tid, iid = trip.id, trip.itineraries[0].id
    assert client.post(f"/trips/{tid}/itineraries/{iid}/schedule-change/dismiss", data={"key": "x"}).status_code == 403
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/upcoming").text).group(1)
    r = client.post(f"/trips/{tid + 1}/itineraries/{iid}/schedule-change/dismiss",
                    data={"key": "x", "csrf_token": token})
    assert r.status_code == 404


def test_migration_0058_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("itineraries")}
        assert "schedule_change_dismissed" in cols()
        command.downgrade(cfg, "0057")
        assert "schedule_change_dismissed" not in cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
