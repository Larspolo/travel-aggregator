"""The event upload reads the .ics files of Google Calendar, Outlook and Apple Calendar alike (#2495).

Each fixture is the "Team day" event of #2492 as its app writes it. Each gives the same two trips (#2494)."""

from datetime import date, time
from pathlib import Path

import pytest

from tests.test_event_trip import _clock, client, count, trips, upload  # noqa: F401  (fixtures and helpers)

EVENTS = Path(__file__).parent / "fixtures" / "events"


@pytest.mark.parametrize("name", ["google.ics", "outlook.ics", "apple.ics"])
def test_each_calendar_app_gives_the_same_two_trips(client, sessions, name):  # noqa: F811
    r = upload(client, (EVENTS / name).read_bytes())
    assert r.status_code == 303
    first, back = trips(sessions)
    assert (first.title, first.origin_text, first.destination_text) == ("Team day", "Amsterdam", "Berlin")
    assert (first.date_from, first.date_to, first.arrive_by, first.leave_after) == (
        date(2026, 12, 21), date(2026, 12, 21), time(9, 0), None)
    assert (back.title, back.origin_text, back.destination_text, back.return_of_id) == (
        "Team day (return)", "Berlin", "Amsterdam", first.id)
    assert (back.date_from, back.date_to, back.leave_after, back.arrive_by) == (
        date(2026, 12, 21), date(2026, 12, 21), time(17, 0), None)
    assert count(sessions) == 2
