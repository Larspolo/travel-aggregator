"""The planned platforms of a leg survive a trip export and its import (#2590); an older export has none (None)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _itinerary

UTC = timezone.utc


def _trip_with_platforms(sessions, from_platform, to_platform, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "IC 515")
        a.legs[0].from_platform = from_platform
        a.legs[0].to_platform = to_platform
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_platforms(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [(leg.from_platform, leg.to_platform) for it in trip.itineraries for leg in it.legs]


def test_the_platforms_of_a_leg_survive_export_and_import(sessions):
    export = _trip_with_platforms(sessions, "8b", "3", "Platforms")
    leg = export["itineraries"][0]["legs"][0]
    assert (leg["from_platform"], leg["to_platform"]) == ("8b", "3")

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_platforms(s, trip_id)
    again_leg = again["itineraries"][0]["legs"][0]
    assert (again_leg["from_platform"], again_leg["to_platform"]) == ("8b", "3")
    assert stored == [("8b", "3")]


def test_an_export_without_the_platform_keys_imports_with_none(sessions):
    export = _trip_with_platforms(sessions, "8b", "3", "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["legs"][0]["from_platform"]
    del old["itineraries"][0]["legs"][0]["to_platform"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_platforms(s, trip_id) == [(None, None)]
