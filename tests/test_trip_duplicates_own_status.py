"""A trip that is not in planning, or is a split part, gets no duplicate warning (#1642)."""

import re
from datetime import date

from app.duplicates import duplicate_trips
from app.models import Trip
from tests.test_trip_duplicates_page import CARD, _add_trip, _set_route
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _trip(s, origin, destination, day, end=None, **kw):
    made = Trip(title=f"{origin} {destination} {day}", origin_text=origin, destination_text=destination,
                date_from=day, date_to=end, **kw)
    s.add(made)
    s.flush()
    return made


def test_an_archived_trip_gives_nothing_even_with_a_matching_trip_in_planning(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1), status="archived")
        _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        s.commit()
        assert duplicate_trips(s, trip) == []


def test_a_booked_trip_gives_nothing_even_with_a_matching_trip_in_planning(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1), status="booked")
        _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        s.commit()
        assert duplicate_trips(s, trip) == []


def test_a_split_part_gives_nothing_even_with_a_matching_trip_in_planning(sessions):
    with sessions() as s:
        parent = _trip(s, "Amsterdam", "Basel", date(2026, 12, 1))
        part = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1), split_of_id=parent.id)
        _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        s.commit()
        assert duplicate_trips(s, part) == []


def test_a_trip_in_planning_still_finds_the_matching_trip(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        other = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        s.commit()
        assert duplicate_trips(s, trip) == [other]


def test_the_page_of_an_archived_trip_shows_no_warning_but_the_planning_trip_does(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_route(sessions, trip_id, "Amsterdam", "Zürich", date(2026, 12, 1))
    ingest(client, auth, trip_id, [offer("89.90")])
    _add_trip(sessions, "Amsterdam", "Zürich", date(2026, 11, 30), date(2026, 12, 2))
    assert re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S) is not None

    with sessions() as s:
        s.get(Trip, trip_id).status = "archived"
        s.commit()
    assert 'id="duplicates"' not in client.get(f"/trips/{trip_id}").text
