"""The bicycle of a trip (#2473): the form, the trip page, the copies, and migration 0064."""

from alembic import command
from sqlalchemy import create_engine, inspect, text
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


def _post(client, tid, **kw):  # noqa: F811
    path = f"/trips/{tid}/edit"
    return client.post(path, data=_form(csrf_token=_token(client, path), **kw), follow_redirects=False)


def _bike(engine, tid):  # noqa: F811
    with Session(engine) as s:
        return s.get(Trip, tid).bike


def _new_id(r):
    return int(r.headers["location"].split("/")[2])


def test_the_checkbox_saves_and_shows_the_bicycle(engine, client):  # noqa: F811
    tid = _new(engine)
    assert _post(client, tid, bike="on").status_code == 303
    assert _bike(engine, tid) is True
    assert "With a bicycle (trip)" in client.get(f"/trips/{tid}").text
    assert 'name="bike" value="on" checked' in client.get(f"/trips/{tid}/edit").text
    assert _post(client, tid, bike="").status_code == 303
    assert _bike(engine, tid) is False
    assert "With a bicycle (trip)" not in client.get(f"/trips/{tid}").text


def test_the_copies_of_a_bicycle_trip_keep_the_bicycle(engine, client):  # noqa: F811
    tid = _new(engine, bike=True)
    token = _token(client, f"/trips/{tid}/edit")
    for action in ("return", "next", "copy"):
        r = client.post(f"/trips/{tid}/{action}", data={"csrf_token": token}, follow_redirects=False)
        assert _bike(engine, _new_id(r)) is True, action
    client.post(f"/trips/{tid}/split", data={"csrf_token": token, "via": "Basel"}, follow_redirects=False)
    with Session(engine) as s:
        splits = s.query(Trip).filter(Trip.split_of_id == tid).all()
        assert len(splits) == 2 and all(t.bike for t in splits)


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0063")
    db = create_engine(empty_database_url)
    try:
        with db.begin() as c:
            c.execute(text("INSERT INTO trips (title, origin_text, destination_text, travelers, status) "
                           "VALUES ('Bern', 'Utrecht', 'Bern', 1, 'planning')"))
        command.upgrade(cfg, "0064")
        with db.connect() as c:
            assert c.execute(text("SELECT bike FROM trips")).scalar_one() is False
        command.downgrade(cfg, "0063")
        assert "bike" not in {c["name"] for c in inspect(db).get_columns("trips")}
    finally:
        db.dispose()
