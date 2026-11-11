"""The hour value of a trip (#2422): the form, the trip page, the copies, and migration 0062."""

from decimal import Decimal

from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_trip_booked import _alembic
from tests.test_trip_forms import _form, _token, client, engine  # noqa: F401 (fixtures)


def _new(engine, **kw):  # noqa: F811
    with Session(engine) as s:
        t = Trip(title="Bern", origin_text="Utrecht", destination_text="Bern", travelers=1, **kw)
        s.add(t)
        s.commit()
        return t.id


def _post(client, tid, value):  # noqa: F811
    path = f"/trips/{tid}/edit"
    return client.post(path, data=_form(hour_value=value, csrf_token=_token(client, path)), follow_redirects=False)


def _value(engine, tid):  # noqa: F811
    with Session(engine) as s:
        return s.get(Trip, tid).hour_value


def test_a_value_is_saved_and_shown_zero_is_kept_and_empty_clears_it(engine, client):  # noqa: F811
    tid = _new(engine)
    assert _post(client, tid, "30").status_code == 303
    assert _value(engine, tid) == Decimal("30")
    assert "Hour value €30/h (trip)" in client.get(f"/trips/{tid}").text
    assert _post(client, tid, "0").status_code == 303
    assert _value(engine, tid) == Decimal("0")
    assert 'name="hour_value" min="0" max="100" step="0.01" value="0' in client.get(f"/trips/{tid}/edit").text
    assert _post(client, tid, "").status_code == 303
    assert _value(engine, tid) is None
    assert "Hour value €" not in client.get(f"/trips/{tid}").text


def test_a_wrong_value_gives_422(engine, client):  # noqa: F811
    tid = _new(engine)
    for value in ("-1", "101", "abc"):
        assert _post(client, tid, value).status_code == 422
    assert _value(engine, tid) is None


def test_the_return_split_and_next_trips_keep_the_value(engine, client):  # noqa: F811
    tid = _new(engine, hour_value=Decimal("30"))
    token = _token(client, f"/trips/{tid}/edit")
    r = client.post(f"/trips/{tid}/return", data={"csrf_token": token}, follow_redirects=False)
    assert _value(engine, int(r.headers["location"].split("/")[2])) == Decimal("30")
    client.post(f"/trips/{tid}/split", data={"csrf_token": token, "via": "Basel"}, follow_redirects=False)
    with Session(engine) as s:
        splits = s.query(Trip).filter(Trip.split_of_id == tid).all()
        assert len(splits) == 2 and all(t.hour_value == Decimal("30") for t in splits)
    r = client.post(f"/trips/{tid}/next", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code in (303, 302)
    assert _value(engine, int(r.headers["location"].split("/")[2])) == Decimal("30")


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0062")
    db = create_engine(empty_database_url)
    try:
        cols = lambda: {c["name"] for c in inspect(db).get_columns("trips")}  # noqa: E731
        assert "hour_value" in cols()
        command.downgrade(cfg, "0061")
        assert "hour_value" not in cols()
    finally:
        db.dispose()
