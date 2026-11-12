""""Repeat" of a trip (#2498): copies every 1 or 2 weeks in one series, the errors, and migration 0065."""

from datetime import date

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import Itinerary, Trip, TripSeries
from tests.test_trip_booked import _alembic
from tests.test_trip_forms import _token, client, engine  # noqa: F401 (fixtures)


def _new(engine, **kw):  # noqa: F811
    values = {"title": "Amsterdam → Berlin", "origin_text": "Amsterdam", "destination_text": "Berlin",
              "travelers": 2, "notes": "window", "date_from": date(2026, 12, 4), "date_to": date(2026, 12, 6)}
    values.update(kw)
    with Session(engine) as s:
        t = Trip(**values)
        s.add(t)
        s.commit()
        return t.id


def _repeat(client, tid, **data):  # noqa: F811
    data.setdefault("csrf_token", _token(client, f"/trips/{tid}/edit"))
    return client.post(f"/trips/{tid}/repeat", data=data, follow_redirects=False)


def _trips(engine):  # noqa: F811
    with Session(engine) as s:
        return [(t.title, t.date_from, t.date_to, t.series_id, t.travelers, t.notes)
                for t in s.query(Trip).order_by(Trip.date_from, Trip.id)]


def test_every_2_weeks_4_dates_makes_3_copies_in_one_series(engine, client):  # noqa: F811
    tid = _new(engine)
    r = _repeat(client, tid, step_weeks="2", count="4")
    assert r.status_code == 303
    rows = _trips(engine)
    assert [row[1] for row in rows] == [date(2026, 12, 4), date(2026, 12, 18), date(2027, 1, 1), date(2027, 1, 15)]
    assert [row[2] for row in rows] == [date(2026, 12, 6), date(2026, 12, 20), date(2027, 1, 3), date(2027, 1, 17)]
    assert len({row[3] for row in rows}) == 1 and rows[0][3] is not None
    assert all(row[0] == "Amsterdam → Berlin" and row[4] == 2 and row[5] == "window" for row in rows)
    with Session(engine) as s:
        assert s.get(TripSeries, rows[0][3]).step_weeks == 2
        assert s.query(Itinerary).count() == 0


def test_every_week_12_dates_and_no_to_date(engine, client):  # noqa: F811
    tid = _new(engine, date_to=None)
    assert _repeat(client, tid, step_weeks="1", count="12").status_code == 303
    rows = _trips(engine)
    assert len(rows) == 12 and rows[-1][1] == date(2027, 2, 19) and all(row[2] is None for row in rows)


@pytest.mark.parametrize("kw,data,reason", [
    ({"date_from": None, "date_to": None}, {}, "no date"),
    ({}, {"step_weeks": "3"}, "1 or 2 weeks"),
    ({}, {"step_weeks": ""}, "1 or 2 weeks"),
    ({}, {"count": "1"}, "2 to 12"),
    ({}, {"count": "13"}, "2 to 12"),
    ({}, {"count": "x"}, "2 to 12"),
])
def test_the_errors_make_no_trip(engine, client, kw, data, reason):  # noqa: F811
    tid = _new(engine, **kw)
    r = _repeat(client, tid, **{"step_weeks": "1", "count": "3", **data})
    assert r.status_code == 422 and reason in r.text
    assert len(_trips(engine)) == 1 and _trips(engine)[0][3] is None


def test_a_trip_in_a_series_a_return_trip_and_a_split_trip_cannot_repeat(engine, client):  # noqa: F811
    tid = _new(engine)
    assert _repeat(client, tid, step_weeks="1", count="2").status_code == 303
    r = _repeat(client, tid, step_weeks="1", count="2")
    assert r.status_code == 422 and "already in a series" in r.text
    out = _new(engine, title="Out")
    back = _new(engine, title="Back", return_of_id=out)
    split = _new(engine, title="Part", split_of_id=out)
    before = len(_trips(engine))
    for t in (out, back):
        r = _repeat(client, t, step_weeks="1", count="2")
        assert r.status_code == 422 and "return trip" in r.text
    r = _repeat(client, split, step_weeks="1", count="2")
    assert r.status_code == 422 and "split trip" in r.text
    assert len(_trips(engine)) == before


def test_the_edit_form_shows_repeat(engine, client):  # noqa: F811
    tid = _new(engine)
    html = client.get(f"/trips/{tid}/edit").text
    assert f'action="/trips/{tid}/repeat"' in html and 'name="step_weeks"' in html and 'name="count"' in html


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0064")
    db = create_engine(empty_database_url)
    try:
        with db.begin() as c:
            c.execute(text("INSERT INTO trips (title, travelers, status) VALUES ('Bern', 1, 'planning')"))
        command.upgrade(cfg, "0065")
        with db.connect() as c:
            assert c.execute(text("SELECT series_id FROM trips")).scalar_one() is None
        command.downgrade(cfg, "0064")
        assert "series_id" not in {c["name"] for c in inspect(db).get_columns("trips")}
        assert "trip_series" not in inspect(db).get_table_names()
        command.upgrade(cfg, "0065")
        assert "series_id" in {c["name"] for c in inspect(db).get_columns("trips")}
    finally:
        db.dispose()
