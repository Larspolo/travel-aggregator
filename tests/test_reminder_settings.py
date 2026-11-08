"""The reminder settings on the messages settings page (#1117): the age N of the newest offers and the days D before departure."""

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


def _shown(c, name):
    return re.search(rf'name="{name}"[^>]*value="([^"]*)"', c.get("/settings/messages").text).group(1)


def _save(c, days, before):
    return c.post("/settings/messages", data={"notify_channel": "none", "ntfy_url": "", "notify_email": "",
                                              "reminder_days": days, "reminder_before_days": before,
                                              "csrf_token": _token(c, "/settings/messages")},
                  follow_redirects=False)


def _stored(sessions, key):
    with sessions() as s:
        row = s.get(Setting, key)
        return row.value if row is not None else None


def test_new_database_has_reminder_off(client):
    assert _shown(client, "reminder_days") == "0"
    assert _shown(client, "reminder_before_days") == "14"


def test_save_stores_both_values(sessions, client):
    r = _save(client, "21", "7")
    assert r.status_code == 303 and r.headers["location"] == "/settings/messages"
    assert _stored(sessions, "reminder_days") == "21"
    assert _stored(sessions, "reminder_before_days") == "7"
    assert _shown(client, "reminder_days") == "21"
    assert _shown(client, "reminder_before_days") == "7"


@pytest.mark.parametrize("bad", ["x", "-1", "400", "1.5"])
def test_bad_value_gets_422_and_stores_nothing(sessions, client, bad):
    assert _save(client, "5", "9").status_code == 303
    r = _save(client, bad, "3")
    assert r.status_code == 422
    assert _stored(sessions, "reminder_days") == "5"
    assert _stored(sessions, "reminder_before_days") == "9"


def test_bad_second_value_stores_nothing(sessions, client):
    assert _save(client, "5", "9").status_code == 303
    assert _save(client, "6", "400").status_code == 422
    assert _stored(sessions, "reminder_days") == "5"
    assert _stored(sessions, "reminder_before_days") == "9"


def test_post_needs_csrf(client):
    r = client.post("/settings/messages", data={"notify_channel": "none", "reminder_days": "3"})
    assert r.status_code in (400, 403)
