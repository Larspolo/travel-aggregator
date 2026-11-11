"""The checked bag of a trip (#2397): the form, the trip page, the copies, and migration 0061."""

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
    return client.post(path, data=_form(checked_bag=value, csrf_token=_token(client, path)), follow_redirects=False)


def _bag(engine, tid):  # noqa: F811
    with Session(engine) as s:
        return s.get(Trip, tid).checked_bag


def test_none_is_saved_and_shown_and_as_the_profile_clears_it(engine, client):  # noqa: F811
    tid = _new(engine)
    assert _post(client, tid, "none").status_code == 303
    assert _bag(engine, tid) == "none"
    assert "No checked bag (trip)" in client.get(f"/trips/{tid}").text
    assert '<option value="none" selected>' in client.get(f"/trips/{tid}/edit").text
    assert _post(client, tid, "").status_code == 303
    assert _bag(engine, tid) is None
    assert "No checked bag (trip)" not in client.get(f"/trips/{tid}").text


def test_another_value_gives_422(engine, client):  # noqa: F811
    tid = _new(engine)
    assert _post(client, tid, "two").status_code == 422
    assert _bag(engine, tid) is None


def test_the_return_trip_and_the_split_trips_keep_none(engine, client):  # noqa: F811
    tid = _new(engine, checked_bag="none")
    token = _token(client, f"/trips/{tid}/edit")
    r = client.post(f"/trips/{tid}/return", data={"csrf_token": token}, follow_redirects=False)
    assert _bag(engine, int(r.headers["location"].split("/")[2])) == "none"
    client.post(f"/trips/{tid}/split", data={"csrf_token": token, "via": "Basel"}, follow_redirects=False)
    with Session(engine) as s:
        splits = s.query(Trip).filter(Trip.split_of_id == tid).all()
        assert len(splits) == 2 and all(t.checked_bag == "none" for t in splits)


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0061")
    db = create_engine(empty_database_url)
    try:
        cols = lambda: {c["name"] for c in inspect(db).get_columns("trips")}  # noqa: E731
        assert "checked_bag" in cols()
        command.downgrade(cfg, "0060")
        assert "checked_bag" not in cols()
    finally:
        db.dispose()
