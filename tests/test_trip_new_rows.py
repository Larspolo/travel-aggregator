"""The "new" mark of the trip page (#1090): the rows first seen after the last full view."""

from alembic import command
from sqlalchemy import create_engine, inspect

from app.models import Trip
from tests.test_trip_booked import _alembic
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

MARK = '<span class="badge new"'


def _viewed(sessions, trip_id):
    with sessions() as s:
        return s.get(Trip, trip_id).viewed_at


def test_the_next_view_marks_only_the_new_rows(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    assert MARK not in client.get(f"/trips/{trip_id}").text  # the first view: no mark
    ingest(client, auth, trip_id, [offer("89.90", "ICE 1"), offer("79.90", "ICE 2")])
    assert client.get(f"/trips/{trip_id}").text.count(MARK) == 2
    assert MARK not in client.get(f"/trips/{trip_id}").text


def test_an_htmx_request_does_not_change_viewed_at(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    client.get(f"/trips/{trip_id}")
    before = _viewed(sessions, trip_id)
    assert before is not None
    client.get(f"/trips/{trip_id}", headers={"HX-Request": "true"})
    assert _viewed(sessions, trip_id) == before


def test_migration_0021_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def has_column():
            return "viewed_at" in {c["name"] for c in inspect(engine).get_columns("trips")}
        assert has_column()
        command.downgrade(cfg, "-1")
        assert not has_column()
        command.upgrade(cfg, "head")
        assert has_column()
    finally:
        engine.dispose()
