"""The exchange rates page of Settings (#384)."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import CurrencyRate

PASSWORD = "pw"


def _token(c, path="/rates"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _rows(sessions):
    with sessions() as s:
        return {r.code: r.eur_per_unit for r in s.scalars(select(CurrencyRate))}


def _save(c, code, rate):
    return c.post("/rates", data={"code": code, "rate": rate, "csrf_token": _token(c)})


def test_add_and_change(client, sessions):
    assert _save(client, "CHF", "1.07").status_code == 200
    assert "1 CHF = €1.07" in client.get("/rates").text
    _save(client, "CHF", "1.1")
    assert _rows(sessions) == {"CHF": Decimal("1.1")}
    assert "1 CHF = €1.1" in client.get("/rates").text


@pytest.mark.parametrize("code,rate", [("CH", "1"), ("chf1", "1"), ("EUR", "1"), ("CHF", "0"), ("CHF", "-1"),
                                       ("CHF", "abc"), ("CHF", "1.1234567"), ("CHF", "NaN")])
def test_bad_input(client, sessions, code, rate):
    r = _save(client, code, rate)
    assert r.status_code == 422
    assert 'class="error"' in r.text
    assert _rows(sessions) == {}


def test_delete(client, sessions):
    _save(client, "GBP", "1.17")
    client.post("/rates/GBP/delete", data={"csrf_token": _token(client)})
    assert _rows(sessions) == {}


def test_login_and_csrf(client, sessions):
    assert client.post("/rates", data={"code": "CHF", "rate": "1"}).status_code in (400, 403)
    anon = TestClient(app)
    assert anon.get("/rates", follow_redirects=False).status_code in (302, 303, 401)
    assert _rows(sessions) == {}


def test_settings_link(client):
    assert 'href="/rates"' in client.get("/settings").text
