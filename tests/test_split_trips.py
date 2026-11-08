"""The split trips of a trip via a place (#1177)."""

from datetime import date

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import ScoreProfile, Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_booked import _alembic


def _trip(sessions, trip_id):
    with sessions() as s:
        profile = ScoreProfile(name="split", config_json={})
        s.add(profile)
        s.flush()
        trip = s.get(Trip, trip_id)
        trip.origin_text, trip.destination_text, trip.travelers = "Amsterdam", "Zürich", 2
        trip.date_from, trip.date_to, trip.profile_id = date(2027, 3, 1), date(2027, 3, 2), profile.id
        s.commit()
        return profile.id


def _splits(sessions, trip_id):
    with sessions() as s:
        return s.scalars(select(Trip).where(Trip.split_of_id == trip_id).order_by(Trip.id)).all()


def _post(c, trip_id, via):
    return c.post(f"/trips/{trip_id}/split", data={"via": via},
                  headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)


def test_split_via_a_place_makes_two_trips(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    profile_id = _trip(sessions, trip_id)
    assert _post(c, trip_id, "Köln").status_code == 303
    first, second = _splits(sessions, trip_id)
    assert (first.title, second.title) == ("Amsterdam → Köln", "Köln → Zürich")
    assert (first.origin_text, first.destination_text) == ("Amsterdam", "Köln")
    assert (second.origin_text, second.destination_text) == ("Köln", "Zürich")
    for t in (first, second):
        assert (t.date_from, t.date_to, t.travelers, t.profile_id) == (date(2027, 3, 1), date(2027, 3, 2), 2,
                                                                       profile_id)
    assert _post(c, trip_id, "Basel").status_code == 303
    assert len(_splits(sessions, trip_id)) == 4


def test_an_empty_place_is_an_error_and_a_split_trip_has_no_split(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _trip(sessions, trip_id)
    assert "Split via" in c.get(f"/trips/{trip_id}/edit").text
    r = _post(c, trip_id, "  ")
    assert r.status_code == 422 and "enter a place" in r.text
    assert _splits(sessions, trip_id) == []
    _post(c, trip_id, "Köln")
    first = _splits(sessions, trip_id)[0]
    assert "Split via" not in c.get(f"/trips/{first.id}/edit").text
    assert _post(c, first.id, "Bonn").status_code == 400


def test_a_delete_of_the_trip_deletes_its_split_trips(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _trip(sessions, trip_id)
    _post(c, trip_id, "Köln")
    r = c.post(f"/trips/{trip_id}/delete", headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert s.scalars(select(Trip)).all() == []


def test_migration_0025_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def has_column():
            return "split_of_id" in {c["name"] for c in inspect(engine).get_columns("trips")}
        assert has_column()
        command.downgrade(cfg, "0024")
        assert not has_column()
        command.upgrade(cfg, "head")
        assert has_column()
    finally:
        engine.dispose()
