"""The trip page offers Dismiss for a timetable change; an arrived journey gets no change (#2359, epic #2339)."""

import re
from datetime import datetime, timedelta, timezone

from tests.test_schedule_change import SEEN, at, client, itinerary  # noqa: F401 (fixture)
from tests.test_schedule_change_pages import MARK, add_trip, changed, squash

from app.models import Trip
from app.schedule_change import schedule_changes

CET = timezone(timedelta(minutes=60))


def test_trip_page_dismiss_hides_the_change(client, sessions):  # noqa: F811
    trip_id = add_trip(sessions, changed())
    html = client.get(f"/trips/{trip_id}").text
    assert MARK in squash(html)
    form = re.search(r'<form class="inline-form" method="post" action="([^"]+/schedule-change/dismiss)">(.*?)</form>',
                     html, re.S)
    assert form is not None and "Dismiss" in form.group(2)
    fields = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', form.group(2)))
    r = client.post(form.group(1), data=fields, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert "Timetable changed" not in client.get(f"/trips/{trip_id}").text


def test_arrived_booked_journey_gets_no_change(sessions):
    trip_id = add_trip(sessions, changed())
    with sessions() as s:
        before_arrival = datetime(2026, 12, 19, tzinfo=CET)
        assert schedule_changes(s, before_arrival), "control: the change shows before the journey arrives"
        after_arrival = datetime(2026, 12, 21, tzinfo=CET)
        assert schedule_changes(s, after_arrival) == {}
        trip = s.get(Trip, trip_id)
        trip.itineraries.append(itinerary("newer", at(9, 0), at(15, 10), SEEN + timedelta(days=2)))
        s.commit()
        assert schedule_changes(s, after_arrival) == {}
