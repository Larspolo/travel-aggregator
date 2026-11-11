"""The rail pass of a trip (#2266): the trip form stores it, the return and split trips copy it, and a deleted pass
gives the trips no pass. The migration 0056 upgrades and downgrades."""

import re
from datetime import date, datetime, timezone

from alembic import command
from sqlalchemy import create_engine, inspect

from app.models import RailPass, Trip
from tests.test_profiles_store import _alembic
from tests.test_rail_pass_page import client, _token  # noqa: F401  (client is a fixture)


def _pass(sessions, name="Interrail"):
    with sessions() as s:
        row = RailPass(name=name, first_day=date(2026, 12, 1), last_day=date(2026, 12, 31),
                       day_cost=40, carriers="", updated_at=datetime.now(timezone.utc))
        s.add(row)
        s.commit()
        return row.id


def _trip(sessions, rail_pass_id=None):
    with sessions() as s:
        t = Trip(title="Utrecht – Berlin", origin_text="Utrecht", destination_text="Berlin",
                 rail_pass_id=rail_pass_id)
        s.add(t)
        s.commit()
        return t.id


def _data(c, path, **kw):
    data = {"title": "Utrecht – Berlin", "travelers": "1", "status": "planning", "notes": "",
            "rail_pass_id": "", "csrf_token": _token(c, path)}
    data.update(kw)
    return data


def test_a_trip_saves_and_shows_its_pass(client, sessions):  # noqa: F811
    pass_id = _pass(sessions)
    trip_id = _trip(sessions)
    path = f"/trips/{trip_id}/edit"
    assert f'<option value="{pass_id}">Interrail</option>' in client.get(path).text
    r = client.post(path, data=_data(client, path, rail_pass_id=str(pass_id)), follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert s.get(Trip, trip_id).rail_pass_id == pass_id
    selected = re.search(r'<option value="(\d+)" selected>Interrail</option>', client.get(path).text)
    assert selected and int(selected.group(1)) == pass_id


def test_no_pass_saves_none(client, sessions):  # noqa: F811
    pass_id = _pass(sessions)
    trip_id = _trip(sessions, rail_pass_id=pass_id)
    path = f"/trips/{trip_id}/edit"
    assert 'value="">No pass</option>' in client.get(path).text
    r = client.post(path, data=_data(client, path, rail_pass_id=""), follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert s.get(Trip, trip_id).rail_pass_id is None


def test_an_unknown_pass_gives_422(client, sessions):  # noqa: F811
    trip_id = _trip(sessions)
    path = f"/trips/{trip_id}/edit"
    r = client.post(path, data=_data(client, path, rail_pass_id="999999"), follow_redirects=False)
    assert r.status_code == 422 and "rail_pass_id: no pass 999999" in r.text
    with sessions() as s:
        assert s.get(Trip, trip_id).rail_pass_id is None


def test_deleting_the_pass_gives_the_trip_no_pass(client, sessions):  # noqa: F811
    pass_id = _pass(sessions)
    trip_id = _trip(sessions, rail_pass_id=pass_id)
    r = client.post(f"/passes/{pass_id}/delete", data={"csrf_token": _token(client)}, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert s.get(RailPass, pass_id) is None
        assert s.get(Trip, trip_id).rail_pass_id is None


def test_the_return_trip_has_the_same_pass(client, sessions):  # noqa: F811
    pass_id = _pass(sessions)
    trip_id = _trip(sessions, rail_pass_id=pass_id)
    r = client.post(f"/trips/{trip_id}/return", data={"csrf_token": _token(client)}, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        ret = s.query(Trip).filter(Trip.return_of_id == trip_id).one()
        assert ret.rail_pass_id == pass_id


def test_the_split_trips_have_the_same_pass(client, sessions):  # noqa: F811
    pass_id = _pass(sessions)
    trip_id = _trip(sessions, rail_pass_id=pass_id)
    r = client.post(f"/trips/{trip_id}/split", data={"via": "Köln", "csrf_token": _token(client)},
                    follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        parts = s.query(Trip).filter(Trip.split_of_id == trip_id).all()
        assert len(parts) == 2 and all(p.rail_pass_id == pass_id for p in parts)


def test_migration_0056_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "rail_pass_id" in {c["name"] for c in inspect(engine).get_columns("trips")}
        command.downgrade(cfg, "0055")
        assert "rail_pass_id" not in {c["name"] for c in inspect(engine).get_columns("trips")}
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
