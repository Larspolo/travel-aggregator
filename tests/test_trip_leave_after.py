"""The "leave after" time of a trip (#2023): the form, the trip page, the cost, copy, export and import, and migration 0050."""

from datetime import time

from alembic import command
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_ingest_best import setup  # noqa: F401 (fixture)
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
    r = client.post(path, data=_form(leave_after=value, csrf_token=_token(client, path)), follow_redirects=False)
    assert r.status_code == 303


def test_the_edit_page_saves_the_time_and_the_trip_page_shows_it(engine, client):  # noqa: F811
    tid = _new(engine)
    _save(client, tid, "17:00")
    with Session(engine) as s:
        assert s.get(Trip, tid).leave_after == time(17, 0)
    assert "Leave after 17:00" in client.get(f"/trips/{tid}").text
    assert 'name="leave_after" value="17:00"' in client.get(f"/trips/{tid}/edit").text


def test_a_blank_field_saves_null_and_the_page_shows_no_time(engine, client):  # noqa: F811
    tid = _new(engine, leave_after=time(9, 30))
    _save(client, tid, "")
    with Session(engine) as s:
        assert s.get(Trip, tid).leave_after is None
    assert "Leave after" not in client.get(f"/trips/{tid}").text.replace('for="f-leave-after">Leave after', "")


def test_copy_trip_keeps_the_time(engine, client):  # noqa: F811
    tid = _new(engine, leave_after=time(17, 0))
    r = client.post(f"/trips/{tid}/copy", data={"csrf_token": _token(client, f"/trips/{tid}/edit")},
                    follow_redirects=False)
    new_id = int(r.headers["location"].split("/")[2])
    with Session(engine) as s:
        assert s.get(Trip, new_id).leave_after == time(17, 0)


def test_the_export_and_the_import_keep_the_time(engine):  # noqa: F811
    tid = _new(engine, leave_after=time(17, 0))
    with Session(engine) as s:
        data = trip_export(load_trip(s, tid))
        assert data["trip"]["leave_after"] == "17:00"
        new_id = import_trip(s, data).trip_id
        s.commit()
    with Session(engine) as s:
        assert s.get(Trip, new_id).leave_after == time(17, 0)
        del data["trip"]["leave_after"]  # an older export
        assert s.get(Trip, import_trip(s, data).trip_id).leave_after is None


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    db = create_engine(empty_database_url)
    try:
        cols = lambda: {c["name"] for c in inspect(db).get_columns("trips")}  # noqa: E731
        assert "leave_after" in cols()
        command.downgrade(cfg, "0049")
        assert "leave_after" not in cols()
        command.upgrade(cfg, "head")
        assert "leave_after" in cols()
        with Session(db) as s:
            assert s.scalars(select(Trip)).all() == []
    finally:
        db.dispose()


ICE = [{"mode": "train", "carrier": "DB", "service_no": "ICE 5", "from_name": "Amsterdam Centraal",
        "to_name": "Köln Hbf", "depart_at": "2026-12-20T14:30:00+01:00", "arrive_at": "2026-12-20T17:00:00+01:00"}]


def test_the_trip_page_breakdown_shows_the_leave_part(setup, sessions):  # noqa: F811
    setup([{"price_amount": "50.00", "price_currency": "EUR", "fare_name": "Sparpreis", "legs": ICE}])
    with sessions() as s:
        trip = s.query(Trip).one()
        trip.leave_after = time(17, 0)
        s.commit()
        trip_id = trip.id
    from tests.test_ingest_best import TestClient, app
    from app.auth import require_login
    app.dependency_overrides[require_login] = lambda: None
    try:
        page = TestClient(app).get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0&leave_hour_markup=20").text
        assert "leave 2 h 30 min before 17:00" in page and "50.00" in page
        assert "100.00" in page  # the price 50.00 and the leave part 50.00
    finally:
        app.dependency_overrides.pop(require_login, None)
