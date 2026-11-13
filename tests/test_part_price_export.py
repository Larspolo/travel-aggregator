"""The part-price mark of a fare survives a trip export and its import (#2657); an older export has none (false)."""

import copy
from datetime import datetime, timezone

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _fare, _itinerary

UTC = timezone.utc


def _trip_with_part_price(sessions, name):
    with sessions() as s:
        t = Trip(title=name, origin_text="A", destination_text="B", travelers=1, status="planning")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 0, "IC 515")
        part = _fare("Teilpreis", (datetime(2026, 11, 10, 9, tzinfo=UTC), "42.00"))
        part.part_price = True
        a.fares.append(part)
        t.itineraries.append(a)
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _imported_part_prices(s, trip_id):
    trip = s.get(Trip, trip_id)
    return [[f.part_price for f in it.fares] for it in trip.itineraries]


def test_the_part_price_survives_export_and_import(sessions):
    export = _trip_with_part_price(sessions, "Part")
    assert export["itineraries"][0]["fares"][0]["part_price"] is True

    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
        stored = _imported_part_prices(s, trip_id)
    assert again["itineraries"][0]["fares"][0]["part_price"] is True
    assert stored == [[True]]


def test_an_export_without_the_key_imports_with_false(sessions):
    export = _trip_with_part_price(sessions, "Older")
    old = copy.deepcopy(export)
    del old["itineraries"][0]["fares"][0]["part_price"]

    with sessions() as s:
        trip_id = import_trip(s, old).trip_id
        s.commit()
        assert _imported_part_prices(s, trip_id) == [[False]]
