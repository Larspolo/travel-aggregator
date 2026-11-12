"""The on-board services of a leg survive a trip export and its import (#2551); an older export has none (None)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _itinerary

UTC = timezone.utc


def _trip_with_services(sessions, services, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "FB 1")
        a.legs[0].services = services
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_services(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [leg.services for it in trip.itineraries for leg in it.legs]


def test_the_services_of_a_leg_survive_export_and_import(sessions):
    export = _trip_with_services(sessions, "wifi,power", "Services")
    assert export["itineraries"][0]["legs"][0]["services"] == "wifi,power"

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_services(s, trip_id)
    assert again["itineraries"][0]["legs"][0]["services"] == "wifi,power"
    assert stored == ["wifi,power"]


def test_an_export_without_the_key_imports_with_none(sessions):
    export = _trip_with_services(sessions, "wifi", "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["legs"][0]["services"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_services(s, trip_id) == [None]
