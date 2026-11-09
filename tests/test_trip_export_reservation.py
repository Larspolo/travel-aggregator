"""The count of legs with a reservation of a fare survives a trip export and its import (#1625)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _fare, _itinerary

UTC = timezone.utc


def _trip_with_fare(sessions, reservation_legs, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "ICE 1")
        f = _fare(name, (datetime(2026, 11, 3, tzinfo=UTC), "89.90"))
        f.reservation_legs = reservation_legs
        a.fares.append(f)
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_fares(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [f.reservation_legs for it in trip.itineraries for f in it.fares]


def test_a_reservation_count_survives_export_and_import(sessions):
    export = _trip_with_fare(sessions, 1, "Reserved")
    assert export["itineraries"][0]["fares"][0]["reservation_legs"] == 1

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_fares(s, trip_id)
    assert again["itineraries"][0]["fares"][0]["reservation_legs"] == 1
    assert stored == [1]


def test_an_export_without_the_key_imports_with_zero(sessions):
    export = _trip_with_fare(sessions, 0, "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["fares"][0]["reservation_legs"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_fares(s, trip_id) == [0]
        assert trip_export(load_trip(s, trip_id))["itineraries"][0]["fares"][0]["reservation_legs"] == 0
