"""The return trip of a one-way trip (#340)."""

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_booked import _alembic


def _trip(sessions, trip_id):
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.origin_text, trip.destination_text, trip.travelers = "Köln", "München", 2
        s.commit()
    return trip_id


def _returns_of(sessions, trip_id):
    with sessions() as s:
        return s.scalars(select(Trip).where(Trip.return_of_id == trip_id)).all()


def _post_return(c, trip_id):
    return c.post(f"/trips/{trip_id}/return", headers={"X-CSRF-Token": _csrf(c, "/settings")},
                  follow_redirects=False)


def test_the_return_trip_has_swapped_places_and_one_link(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _trip(sessions, trip_id)
    r = _post_return(c, trip_id)
    assert r.status_code == 303
    [ret] = _returns_of(sessions, trip_id)
    assert r.headers["location"] == f"/trips/{ret.id}/edit"
    assert (ret.origin_text, ret.destination_text, ret.travelers) == ("München", "Köln", 2)
    assert ret.title.endswith(" (return)") and ret.date_from is None
    r2 = _post_return(c, trip_id)
    assert r2.status_code == 303 and r2.headers["location"] == f"/trips/{ret.id}/edit"
    assert len(_returns_of(sessions, trip_id)) == 1


def test_a_return_trip_cannot_have_a_return_trip(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _post_return(c, trip_id)
    [ret] = _returns_of(sessions, trip_id)
    assert _post_return(c, ret.id).status_code == 400


def test_a_request_without_the_csrf_token_is_refused(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert c.post(f"/trips/{trip_id}/return", follow_redirects=False).status_code == 403
    assert _returns_of(sessions, trip_id) == []


def test_the_button_shows_only_for_an_outbound_trip_without_return(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert "Make the return trip" in c.get(f"/trips/{trip_id}").text
    _post_return(c, trip_id)
    [ret] = _returns_of(sessions, trip_id)
    assert "Make the return trip" not in c.get(f"/trips/{trip_id}").text
    assert "Make the return trip" not in c.get(f"/trips/{ret.id}").text


def test_deleting_the_outbound_trip_keeps_the_return_trip(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _post_return(c, trip_id)
    [ret] = _returns_of(sessions, trip_id)
    with sessions() as s:
        s.delete(s.get(Trip, trip_id))
        s.commit()
    with sessions() as s:
        assert s.get(Trip, ret.id).return_of_id is None


def test_migration_0011_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def has_column():
            return "return_of_id" in {c["name"] for c in inspect(engine).get_columns("trips")}
        assert has_column()
        command.downgrade(cfg, "0010")
        assert not has_column()
        command.upgrade(cfg, "head")
        assert has_column()
    finally:
        engine.dispose()
