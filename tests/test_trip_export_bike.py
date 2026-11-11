"""The bicycle values of a trip and its fares survive a JSON export and its import (#2477)."""

import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _fare, _itinerary

UTC = timezone.utc


def _trip_with_bike(sessions, trip_bike, fare_bike, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning", bike=trip_bike)
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "ICE 1")
        f = _fare(name, (datetime(2026, 11, 3, tzinfo=UTC), "89.90"))
        f.bike = fare_bike
        a.fares.append(f)
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _stored(s, trip_id):
    trip = s.get(Trip, trip_id)
    return trip.bike, [f.bike for it in trip.itineraries for f in it.fares]


def test_a_bicycle_trip_with_a_reservation_fare_survives_export_and_import(sessions):
    export = _trip_with_bike(sessions, True, "reservation", "Bike")
    assert export["trip"]["bike"] is True
    assert export["itineraries"][0]["fares"][0]["bike"] == "reservation"

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        assert _stored(s, trip_id) == (True, ["reservation"])


def test_an_export_without_the_bike_keys_imports_with_none_and_false(sessions):
    export = _trip_with_bike(sessions, True, "allowed", "Older")
    old = copy.deepcopy(export)
    del old["trip"]["bike"]
    del old["itineraries"][0]["fares"][0]["bike"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _stored(s, trip_id) == (False, [None])


def test_an_unknown_fare_value_is_an_error_and_nothing_is_stored(sessions):
    export = _trip_with_bike(sessions, False, "allowed", "Bad")
    export["itineraries"][0]["fares"][0]["bike"] = "maybe"

    with sessions() as s:
        before = s.scalar(select(func.count()).select_from(Trip))
        with pytest.raises(ValueError):
            import_trip(s, export)
        s.rollback()
        assert s.scalar(select(func.count()).select_from(Trip)) == before
