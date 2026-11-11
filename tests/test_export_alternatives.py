"""The alternative origins and destinations in the JSON export and the import of a trip (#1425)."""

import copy
from datetime import date

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export


def _trip(sessions, **kw):
    with sessions() as s:
        t = Trip(title="Amsterdam – Basel", origin_text="Amsterdam", destination_text="Zürich",
                 destination_alt_text="Basel", date_from=date(2026, 12, 1), travelers=1, status="planning", **kw)
        s.add(t)
        s.commit()
        return t.id


def test_the_export_has_the_alternative_places(sessions):
    trip_id = _trip(sessions)
    with sessions() as s:
        data = trip_export(load_trip(s, trip_id))
    assert data["trip"]["origin_alt"] is None
    assert data["trip"]["destination_alt"] == "Basel"


def test_an_import_into_an_empty_database_keeps_the_other_destination(sessions):
    trip_id = _trip(sessions)
    with sessions() as s:
        data = trip_export(load_trip(s, trip_id))
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        new_trip = s.get(Trip, r.trip_id)
        assert new_trip.destination_alt_text == "Basel"
        assert new_trip.origin_alt_text is None
        assert new_trip.destination_text == "Zürich"


def test_an_export_with_the_alternatives_round_trips_the_same(sessions):
    trip_id = _trip(sessions, origin_alt_text="Rotterdam, Utrecht")
    with sessions() as s:
        data = trip_export(load_trip(s, trip_id))
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        again = trip_export(load_trip(s, r.trip_id))
    assert again["trip"]["origin_alt"] == "Rotterdam, Utrecht"
    assert again["trip"]["destination_alt"] == "Basel"


def test_an_older_export_without_the_keys_imports_as_before(sessions):
    trip_id = _trip(sessions)
    with sessions() as s:
        data = trip_export(load_trip(s, trip_id))
    del data["trip"]["origin_alt"]
    del data["trip"]["destination_alt"]
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        new_trip = s.get(Trip, r.trip_id)
        assert new_trip.origin_alt_text is None
        assert new_trip.destination_alt_text is None
        assert new_trip.destination_text == "Zürich"
        assert new_trip.title == "Amsterdam – Basel"
