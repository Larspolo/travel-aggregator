"""The expected load of a leg survives a trip export and its import (#2584); an older export has none (None)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _itinerary

UTC = timezone.utc


def _trip_with_load(sessions, load_first, load_second, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "FB 1")
        a.legs[0].load_first = load_first
        a.legs[0].load_second = load_second
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_loads(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [(leg.load_first, leg.load_second) for it in trip.itineraries for leg in it.legs]


def test_the_load_of_a_leg_survives_export_and_import(sessions):
    export = _trip_with_load(sessions, 2, 4, "Load")
    assert export["itineraries"][0]["legs"][0]["load_second"] == 4

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_loads(s, trip_id)
    assert again["itineraries"][0]["legs"][0]["load_first"] == 2
    assert again["itineraries"][0]["legs"][0]["load_second"] == 4
    assert stored == [(2, 4)]


def test_an_export_without_the_load_keys_imports_with_none(sessions):
    export = _trip_with_load(sessions, 1, 3, "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["legs"][0]["load_first"]
    del old["itineraries"][0]["legs"][0]["load_second"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_loads(s, trip_id) == [(None, None)]
