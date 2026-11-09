"""The "arrive by" time of a trip (#1294): the form, the trip page, copy, export and import, and migration 0027."""

from datetime import time

from alembic import command
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_booked import _alembic
from tests.test_trip_forms import _form, _token, client, engine  # noqa: F401 (fixtures)


def _new(engine, **kw):  # noqa: F811
    with Session(engine) as s:
        t = Trip(title="Bern", travelers=1, **kw)
        s.add(t)
        s.commit()
        return t.id


def _save(client, tid, value):  # noqa: F811
    path = f"/trips/{tid}/edit"
    r = client.post(path, data=_form(arrive_by=value, csrf_token=_token(client, path)), follow_redirects=False)
    assert r.status_code == 303


def test_the_edit_page_saves_the_time_and_the_trip_page_shows_it(engine, client):  # noqa: F811
    tid = _new(engine)
    _save(client, tid, "14:00")
    with Session(engine) as s:
        assert s.get(Trip, tid).arrive_by == time(14, 0)
    assert "Arrive by 14:00" in client.get(f"/trips/{tid}").text
    assert 'name="arrive_by" value="14:00"' in client.get(f"/trips/{tid}/edit").text


def test_a_blank_field_saves_null_and_the_page_shows_no_time(engine, client):  # noqa: F811
    tid = _new(engine, arrive_by=time(9, 30))
    _save(client, tid, "")
    with Session(engine) as s:
        assert s.get(Trip, tid).arrive_by is None
    assert "Arrive by" not in client.get(f"/trips/{tid}").text.replace('for="f-arrive-by">Arrive by', "")


def test_copy_trip_keeps_the_time(engine, client):  # noqa: F811
    tid = _new(engine, arrive_by=time(14, 0))
    r = client.post(f"/trips/{tid}/copy", data={"csrf_token": _token(client, f"/trips/{tid}/edit")},
                    follow_redirects=False)
    new_id = int(r.headers["location"].split("/")[2])
    with Session(engine) as s:
        assert s.get(Trip, new_id).arrive_by == time(14, 0)


def test_the_export_and_the_import_keep_the_time(engine):  # noqa: F811
    tid = _new(engine, arrive_by=time(14, 0))
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        assert data["trip"]["arrive_by"] == "14:00"
        new_id = import_trip(s, data).trip_id
        s.commit()
    with Session(engine) as s:
        assert s.get(Trip, new_id).arrive_by == time(14, 0)
        del data["trip"]["arrive_by"]  # an older export
        assert s.get(Trip, import_trip(s, data).trip_id).arrive_by is None


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    db = create_engine(empty_database_url)
    try:
        cols = lambda: {c["name"] for c in inspect(db).get_columns("trips")}  # noqa: E731
        assert "arrive_by" in cols()
        command.downgrade(cfg, "0026")
        assert "arrive_by" not in cols()
        command.upgrade(cfg, "head")
        assert "arrive_by" in cols()
        with Session(db) as s:
            assert s.scalars(select(Trip)).all() == []
    finally:
        db.dispose()
