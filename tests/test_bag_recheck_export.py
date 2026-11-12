"""The bag recheck of a leg survives a trip export and its import (#2663); an older export has none (None)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _itinerary

UTC = timezone.utc


def _trip_with_recheck(sessions, bag_recheck, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "IC 515")
        a.legs[0].bag_recheck = bag_recheck
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_recheck(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [leg.bag_recheck for it in trip.itineraries for leg in it.legs]


def test_a_true_recheck_survives_export_and_import(sessions):
    export = _trip_with_recheck(sessions, True, "Recheck yes")
    assert export["itineraries"][0]["legs"][0]["bag_recheck"] is True

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_recheck(s, trip_id)
    assert again["itineraries"][0]["legs"][0]["bag_recheck"] is True
    assert stored == [True]


def test_a_false_recheck_survives_export_and_import(sessions):
    export = _trip_with_recheck(sessions, False, "Recheck no")
    assert export["itineraries"][0]["legs"][0]["bag_recheck"] is False

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        stored = _imported_recheck(s, trip_id)
    assert stored == [False]


def test_an_export_without_the_recheck_key_imports_with_none(sessions):
    export = _trip_with_recheck(sessions, True, "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["legs"][0]["bag_recheck"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_recheck(s, trip_id) == [None]
