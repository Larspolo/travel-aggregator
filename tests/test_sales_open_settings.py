"""The booking horizon per source on the messages settings page (#2255, epic #2252)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.sales_open import horizons
from tests.test_settings_page import PASSWORD, _token


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _shown(c):
    return re.search(r'name="horizon_bahn.de"[^>]*value="([^"]*)"', c.get("/settings/messages").text).group(1)


def _save(c, days):
    data = {"horizon_bahn.de": days, "csrf_token": _token(c, "/settings/messages")}
    return c.post("/settings/sales-open", data=data, follow_redirects=False)


def _stored(sessions):
    with sessions() as s:
        return horizons(s)


def test_save_180_and_blank_removes(sessions, client):
    assert _shown(client) == ""
    r = _save(client, "180")
    assert r.status_code == 303 and r.headers["location"] == "/settings/messages"
    assert _shown(client) == "180"
    assert _stored(sessions) == {"bahn.de": 180}
    _save(client, "")
    assert _shown(client) == ""
    assert _stored(sessions) == {}


@pytest.mark.parametrize("bad", ["0", "1000", "abc", "-5", "1.5"])
def test_bad_value_shows_message_and_keeps_old(sessions, client, bad):
    _save(client, "180")
    _save(client, bad)
    page = client.get("/settings/messages").text
    assert "must be a whole number from 1 to 999" in page
    assert _shown(client) == "180"
    assert _stored(sessions) == {"bahn.de": 180}
