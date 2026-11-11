"""The access and egress places page (#97)."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import AccessTime

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _add(c, **values):
    data = {"place_text": "home → Amsterdam Centraal", "kind": "access", "minutes": "35", "cost": "0"} | values
    return c.post("/places", data=data | {"csrf_token": _token(c, "/places")}, follow_redirects=False)


def test_no_login_redirects():
    r = TestClient(app).get("/places", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=%2F")  # the target of #2103


def test_add_list_and_delete(sessions, client):
    assert _add(client, place_text="home <b>", cost="2.5").status_code == 303
    with sessions() as s:
        p = s.scalars(select(AccessTime)).one()
        assert (p.place_text, p.kind, p.minutes, p.cost) == ("home <b>", "access", 35, Decimal("2.50"))
        place_id = p.id
    page = client.get("/places").text
    assert "home &lt;b&gt;" in page and "35 min" in page and "€2.50" in page
    assert client.post(f"/places/{place_id}/delete", follow_redirects=False).status_code == 403
    r = client.post(f"/places/{place_id}/delete", data={"csrf_token": _token(client, "/places")},
                    follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert s.scalars(select(AccessTime)).all() == []


@pytest.mark.parametrize("bad", [{"minutes": "-1"}, {"cost": "-0.01"}, {"place_text": "  "}, {"kind": "walk"},
                                 {"minutes": "x"}, {"cost": "NaN"}])
def test_bad_value_gives_422_and_stores_nothing(sessions, client, bad):
    assert _add(client, **bad).status_code == 422
    with sessions() as s:
        assert s.scalars(select(AccessTime)).all() == []


def test_add_needs_csrf(sessions, client):
    r = client.post("/places", data={"place_text": "x", "kind": "access", "minutes": "1", "cost": "0"},
                    follow_redirects=False)
    assert r.status_code == 403
