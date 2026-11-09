"""The calendar link still works after "Log out on all other devices" (#1281)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash, token_limiter
from app.calendar_feed import new_feed_token
from app.main import app

PASSWORD = "correct horse"


@pytest.fixture(autouse=True)
def _limiter():
    token_limiter.reset()
    yield
    token_limiter.reset()


@pytest.fixture
def setup(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = new_feed_token(s)
        s.commit()
    return token


def _csrf(client, path="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _login(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303


def _end_others(client):
    return client.post("/settings/sessions/end-others", data={"csrf_token": _csrf(client, "/settings")},
                       follow_redirects=False)


def test_the_calendar_link_still_works_after_log_out_on_other_devices(setup):
    token = setup
    client = TestClient(app)
    _login(client)
    assert client.get(f"/calendar/{token}.ics").status_code == 200
    assert _end_others(client).status_code == 303
    assert TestClient(app).get(f"/calendar/{token}.ics").status_code == 200
