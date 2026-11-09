"""The travel-day message setting on the messages settings page (#1650): the hours H before a booked journey, 0 is off."""

import re

import pytest

from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Setting
from tests.test_settings_page import PASSWORD, _token


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _shown(c):
    return re.search(r'name="travel_day_hours"[^>]*value="([^"]*)"', c.get("/settings/messages").text).group(1)


def _save(c, hours=None):
    data = {"notify_channel": "none", "ntfy_url": "", "notify_email": "",
            "csrf_token": _token(c, "/settings/messages")}
    if hours is not None:
        data["travel_day_hours"] = hours
    return c.post("/settings/messages", data=data, follow_redirects=False)


def _stored(sessions):
    with sessions() as s:
        row = s.get(Setting, "travel_day_hours")
        return row.value if row is not None else None


def test_new_database_has_travel_day_off(client):
    assert _shown(client) == "0"


def test_save_24_stores_and_shows_24(sessions, client):
    r = _save(client, "24")
    assert r.status_code == 303 and r.headers["location"] == "/settings/messages"
    assert _stored(sessions) == "24"
    assert _shown(client) == "24"


def test_save_0_turns_it_off(sessions, client):
    assert _save(client, "24").status_code == 303
    assert _save(client, "0").status_code == 303
    assert _stored(sessions) == "0"
    assert _shown(client) == "0"


@pytest.mark.parametrize("bad", ["-1", "73", "abc", "1.5", ""])
def test_bad_value_gets_422_and_keeps_stored_value(sessions, client, bad):
    assert _save(client, "12").status_code == 303
    r = _save(client, bad)
    assert r.status_code == 422
    assert _stored(sessions) == "12"


def test_form_without_the_field_keeps_stored_value(sessions, client):
    assert _save(client, "48").status_code == 303
    assert _save(client).status_code == 303
    assert _stored(sessions) == "48"
    assert _shown(client) == "48"
