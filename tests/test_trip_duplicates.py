"""The other trips in planning of the same journey as a trip (#1591)."""

from datetime import date

from app.duplicates import duplicate_trips
from app.models import Trip


def _trip(s, origin, destination, day, end=None, **kw):
    trip = Trip(title=f"{origin} {destination} {day}", origin_text=origin, destination_text=destination,
                date_from=day, date_to=end, **kw)
    s.add(trip)
    s.flush()
    return trip


def test_a_trip_in_planning_with_overlapping_dates_on_the_same_route_is_a_duplicate(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        other = _trip(s, "amsterdam", "Zurich", date(2026, 11, 30), date(2026, 12, 2))
        s.commit()
        assert duplicate_trips(s, trip) == [other]


def test_the_alias_of_a_place_also_counts(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        other = _trip(s, "Amsterdam", "Zürich HB", date(2026, 12, 1))
        s.commit()
        assert duplicate_trips(s, trip) == [other]


def test_another_route_a_later_date_and_no_dates_give_nothing(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        _trip(s, "Amsterdam", "Basel", date(2026, 12, 1))
        _trip(s, "Amsterdam", "Zürich", date(2026, 12, 8))
        _trip(s, "Amsterdam", "Zürich", None)
        s.commit()
        assert duplicate_trips(s, trip) == []


def test_an_archived_trip_and_a_split_part_give_nothing(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1), status="archived")
        _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1), split_of_id=trip.id)
        s.commit()
        assert duplicate_trips(s, trip) == []


def test_the_trip_itself_and_a_trip_without_a_start_date_give_nothing(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        _trip(s, "Amsterdam", "Zürich", None)
        s.commit()
        assert duplicate_trips(s, trip) == []
        undated = _trip(s, "Amsterdam", "Zürich", None)
        s.commit()
        assert duplicate_trips(s, undated) == []


def test_results_are_ordered_by_id(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1))
        first = _trip(s, "Amsterdam", "Zürich", date(2026, 11, 30), date(2026, 12, 1))
        second = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 1), date(2026, 12, 4))
        s.commit()
        assert duplicate_trips(s, trip) == [first, second]
