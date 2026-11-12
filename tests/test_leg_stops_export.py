"""The stops of a leg survive a trip export and its import (#2636); an older export has no stops (None)."""

import copy
from datetime import datetime, timezone

from app.models import LegStop, Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _itinerary

UTC = timezone.utc


def _trip_with_stops(sessions, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 60, "IC 515")
        a.legs[0].stops.extend([
            LegStop(seq=1, name="Utrecht", code="UT", arrive_at=datetime(2026, 12, 1, 8, 30, tzinfo=UTC),
                    arrive_offset_min=60, depart_at=datetime(2026, 12, 1, 8, 35, tzinfo=UTC), depart_offset_min=60,
                    platform="3", note=None),
            LegStop(seq=2, name="Arnhem", code="AH", arrive_at=datetime(2026, 12, 1, 10, tzinfo=UTC),
                    arrive_offset_min=60, depart_at=datetime(2026, 12, 1, 10, 4, tzinfo=UTC), depart_offset_min=60,
                    platform="8b", note="Change"),
        ])
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_stops(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [
        [(x.seq, x.name, x.code, x.arrive_at, x.arrive_offset_min, x.depart_at, x.depart_offset_min, x.platform, x.note)
         for x in leg.stops]
        for it in trip.itineraries for leg in it.legs
    ]


def test_the_stops_of_a_leg_survive_export_and_import(sessions):
    export = _trip_with_stops(sessions, "Stops")
    stops = export["itineraries"][0]["legs"][0]["stops"]
    assert [(x["name"], x["code"], x["platform"], x["note"]) for x in stops] == [
        ("Utrecht", "UT", "3", None), ("Arnhem", "AH", "8b", "Change")]
    assert stops[0]["arrive_at"] == "2026-12-01T09:30:00+01:00"

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_stops(s, trip_id)
    assert again["itineraries"][0]["legs"][0]["stops"] == stops
    assert stored == [[
        (1, "Utrecht", "UT", datetime(2026, 12, 1, 8, 30, tzinfo=UTC), 60,
         datetime(2026, 12, 1, 8, 35, tzinfo=UTC), 60, "3", None),
        (2, "Arnhem", "AH", datetime(2026, 12, 1, 10, tzinfo=UTC), 60,
         datetime(2026, 12, 1, 10, 4, tzinfo=UTC), 60, "8b", "Change"),
    ]]


def test_an_export_without_the_stops_key_imports_a_leg_with_no_stops(sessions):
    export = _trip_with_stops(sessions, "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["legs"][0]["stops"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_stops(s, trip_id) == [[]]
