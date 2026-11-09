"""The other origins and destinations of a trip (#1422)."""

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import Trip
from app.trips import alt_places
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_booked import _alembic


def test_alt_places():
    assert alt_places("Basel, , Bern") == ["Basel", "Bern"]
    assert alt_places(None) == []
    assert alt_places("  ") == []


def _save(c, trip_id):
    data = {"title": "Ski", "origin_text": "Amsterdam", "destination_text": "Zürich",
            "destination_alt_text": "Basel, Bern", "travelers": "1", "status": "planning"}
    return c.post(f"/trips/{trip_id}/edit", data=data, headers={"X-CSRF-Token": _csrf(c, "/settings")},
                  follow_redirects=False)


def test_the_trip_page_and_form_show_the_other_places(setup):  # noqa: F811
    c, _, trip_id = setup
    assert _save(c, trip_id).status_code == 303
    assert "Amsterdam → Zürich or Basel or Bern" in c.get(f"/trips/{trip_id}").text
    form = c.get(f"/trips/{trip_id}/edit").text
    assert 'value="Basel, Bern"' in form and "Other origins (comma-separated)" in form


def test_the_return_trip_swaps_and_the_copy_keeps_the_other_places(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _save(c, trip_id)
    h = {"X-CSRF-Token": _csrf(c, "/settings")}
    assert c.post(f"/trips/{trip_id}/return", headers=h, follow_redirects=False).status_code == 303
    assert c.post(f"/trips/{trip_id}/copy", headers=h, follow_redirects=False).status_code == 303
    with sessions() as s:
        ret = s.scalar(select(Trip).where(Trip.return_of_id == trip_id))
        assert (ret.origin_alt_text, ret.destination_alt_text) == ("Basel, Bern", None)
        copy = s.scalar(select(Trip).where(Trip.title.like("%(copy)")))
        assert copy.destination_alt_text == "Basel, Bern"


def test_migration_0030_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("trips")}
        assert {"origin_alt_text", "destination_alt_text"} <= cols()
        command.downgrade(cfg, "0029")
        assert not {"origin_alt_text", "destination_alt_text"} & cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
