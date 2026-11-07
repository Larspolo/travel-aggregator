"""The create and edit forms of a trip (#22)."""

import re
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Itinerary, Trip

PASSWORD = "pw"
T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _form(**kw):
    data = {"title": "Berlin", "origin_text": "Utrecht", "destination_text": "Berlin", "date_from": "2026-12-01",
            "date_to": "2026-12-05", "travelers": "2", "status": "planning", "notes": ""}
    data.update(kw)
    return data


def test_create(engine, client):
    r = client.post("/trips/new", data=_form(csrf_token=_token(client, "/trips/new")), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    html = client.get("/").text
    assert "Utrecht → Berlin" in html and 'href="/trips/new"' in html
    with Session(engine) as s:
        t = s.scalars(select(Trip)).one()
        assert (t.travelers, t.date_to, t.notes) == (2, date(2026, 12, 5), None)


def test_edit_keeps_offers(engine, client):
    with Session(engine) as s:
        t = Trip(title="Old", travelers=1)
        s.add_all([t, Itinerary(trip=t, fingerprint="f", depart_at=T, arrive_at=T, duration_min=60)])
        s.commit()
        tid = t.id
    path = f"/trips/{tid}/edit"
    assert 'value="Old"' in client.get(path).text
    r = client.post(path, data=_form(title="New", status="booked", csrf_token=_token(client, path)),
                    follow_redirects=False)
    assert r.status_code == 303
    with Session(engine) as s:
        t = s.get(Trip, tid)
        assert (t.title, t.status, t.travelers) == ("New", "booked", 2)
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 1


@pytest.mark.parametrize("bad", [{"title": " "}, {"date_to": "2026-11-30"}, {"travelers": "10"},
                                 {"status": "lost"}])
def test_invalid_stores_nothing(engine, client, bad):
    r = client.post("/trips/new", data=_form(csrf_token=_token(client, "/trips/new"), **bad))
    assert r.status_code == 422 and 'class="errors"' in r.text
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Trip)) == 0


def test_missing_trip(engine, client):
    assert client.get("/trips/999/edit").status_code == 404


def test_needs_csrf(engine, client):
    assert client.post("/trips/new", data=_form()).status_code == 403
