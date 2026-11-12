"""The notices of a connection survive a trip export and its import (#2639); an older export has none (None)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _itinerary

UTC = timezone.utc
NOTICE = {"text": "Track repairs", "level": "warning", "leg": 1}


def _trip_with_notices(sessions, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "IC 515",
                       notices=[NOTICE])
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_notices(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [it.notices for it in trip.itineraries]


def test_the_notices_of_an_itinerary_survive_export_and_import(sessions):
    export = _trip_with_notices(sessions, "Notices")
    assert export["itineraries"][0]["notices"] == [NOTICE]

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_notices(s, trip_id)
    assert again["itineraries"][0]["notices"] == [NOTICE]
    assert stored == [[NOTICE]]


def test_an_export_without_the_notices_key_imports_with_none(sessions):
    export = _trip_with_notices(sessions, "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["notices"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_notices(s, trip_id) == [None]
