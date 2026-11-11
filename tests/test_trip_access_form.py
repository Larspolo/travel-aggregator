"""The access times of a trip on its edit page (#2110)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import AccessTime, Trip, TripAccessTime

PASSWORD = "pw"


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def trips(engine):
    with Session(engine) as s:
        a, b = Trip(title="One"), Trip(title="Two")
        s.add_all([a, b, AccessTime(place_text="Zürich HB", kind="egress", minutes=20, cost=0)])
        s.commit()
        return a.id, b.id


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _post(c, trip_id, **kw):
    data = {"place_text": "Zürich HB", "kind": "egress", "minutes": "10", "cost": "0"}
    data.update(kw)
    data["csrf_token"] = _token(c, f"/trips/{trip_id}/edit")
    return c.post(f"/trips/{trip_id}/places", data=data, follow_redirects=False)


def _rows(engine):
    with Session(engine) as s:
        return [(p.trip_id, p.place_text, p.minutes) for p in s.scalars(select(TripAccessTime))]


def test_an_override_is_added_and_listed_only_on_its_trip(engine, client, trips):
    one, two = trips
    assert _post(client, one).status_code == 303
    page = client.get(f"/trips/{one}/edit").text
    assert "Access times of this trip" in page and "10 min" in page and "global: 20 min" in page
    assert "10 min" not in client.get(f"/trips/{two}/edit").text


def test_a_second_post_changes_the_row_and_bad_values_store_nothing(engine, client, trips):
    one, _ = trips
    _post(client, one)
    _post(client, one, place_text="zürich hb", minutes="15")
    assert [(r[0], r[2]) for r in _rows(engine)] == [(one, 15)]
    assert _post(client, one, place_text="Bern", minutes="-1").status_code == 422
    assert _post(client, one, place_text="  ").status_code == 422
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(TripAccessTime)) == 1


def test_a_delete_through_another_trip_gives_404(engine, client, trips):
    one, two = trips
    _post(client, one)
    with Session(engine) as s:
        pid = s.scalars(select(TripAccessTime)).one().id
    token = _token(client, f"/trips/{two}/edit")
    assert client.post(f"/trips/{two}/places/{pid}/delete", data={"csrf_token": token}).status_code == 404
    assert len(_rows(engine)) == 1
    r = client.post(f"/trips/{one}/places/{pid}/delete", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303 and _rows(engine) == []
