"""The tags of a trip in the JSON export and the import of a trip (#1952)."""

import copy
from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export


def _trip(sessions, tags_text=None):
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 1), travelers=1, status="planning", tags_text=tags_text)
        s.add(t)
        s.commit()
        return t.id


def _export(sessions, trip_id):
    with sessions() as s:
        return trip_export(load_trip(s, trip_id))


def _trip_count(sessions):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(Trip))


def test_the_export_has_the_tags_as_a_list(sessions):
    trip_id = _trip(sessions, tags_text="work, Zürich")
    assert _export(sessions, trip_id)["trip"]["tags"] == ["work", "Zürich"]


def test_an_export_with_the_tags_round_trips_the_same(sessions):
    trip_id = _trip(sessions, tags_text="work, Zürich")
    data = _export(sessions, trip_id)
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        new_trip = s.get(Trip, r.trip_id)
        assert new_trip.tags_text == "work, Zürich"
    assert _export(sessions, r.trip_id)["trip"]["tags"] == ["work", "Zürich"]


def test_a_trip_without_tags_exports_an_empty_list_and_imports_none(sessions):
    trip_id = _trip(sessions, tags_text=None)
    data = _export(sessions, trip_id)
    assert data["trip"]["tags"] == []
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        assert s.get(Trip, r.trip_id).tags_text is None


def test_an_older_export_without_the_tags_imports_with_none(sessions):
    trip_id = _trip(sessions, tags_text="work")
    data = _export(sessions, trip_id)
    del data["trip"]["tags"]
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        new_trip = s.get(Trip, r.trip_id)
        assert new_trip.tags_text is None
        assert new_trip.title == "Amsterdam – Zürich"


@pytest.mark.parametrize("tags", [
    ["a", "b", "c", "d", "e", "f"],   # 6 tags
    ["x" * 21],                       # a tag of 21 characters
])
def test_an_import_with_too_many_or_too_long_tags_stores_no_trip(sessions, tags):
    trip_id = _trip(sessions, tags_text="work")
    data = _export(sessions, trip_id)
    data["trip"]["tags"] = tags
    before = _trip_count(sessions)
    with sessions() as s:
        with pytest.raises(ValueError):
            import_trip(s, copy.deepcopy(data))
        s.rollback()
    assert _trip_count(sessions) == before
