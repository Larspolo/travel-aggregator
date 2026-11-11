"""Turn the second login step on and off on the settings page (#1314)."""

import re
import time

import pytest
from fastapi.testclient import TestClient

from app import totp
from app.auth import TOTP_SECRET, TOTP_STEP, make_password_hash
from app.main import app
from app.models import Setting

PASSWORD = "correct horse"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    _login(c)
    return c


def _csrf(client, path="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _login(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303


def _post(client, path, **data):
    return client.post(path, data={"csrf_token": _csrf(client, "/settings"), **data}, follow_redirects=False)


def _rows(sessions):
    with sessions() as s:
        return {k: s.get(Setting, k) for k in (TOTP_SECRET, TOTP_STEP)}


def _start(client):
    assert _post(client, "/settings/totp/start").status_code == 303
    page = client.get("/settings").text
    key = re.search(r'class="totp-key">([A-Z2-7 ]+)<', page).group(1)
    return page, key.replace(" ", "")


def _card(page):
    return page[page.index('id="totp"'):]


def _turn_on(client):
    _, secret = _start(client)
    assert _post(client, "/settings/totp/on", code=totp.code(secret, time.time())).status_code == 303
    return secret


def test_off_then_start_shows_the_key_and_saves_nothing(client, sessions):
    card = _card(client.get("/settings").text)
    assert "Off" in card and "Turn on" in card
    page, secret = _start(client)
    assert len(secret) == 32 and "otpauth://totp/" in page and secret in page and "Code from the app" in page
    assert re.search(r'class="totp-key">(\w{4} ){7}\w{4}<', page)
    assert all(v is None for v in _rows(sessions).values())


def test_wrong_code_keeps_it_off(client, sessions):
    _start(client)
    _post(client, "/settings/totp/on", code="000000x")
    assert "Wrong code." in client.get("/settings").text
    assert _rows(sessions)[TOTP_SECRET] is None


def test_correct_code_turns_on_and_off(client, sessions):
    secret = _turn_on(client)
    card = _card(client.get("/settings").text)
    assert "On" in card and "Turn off" in card
    rows = _rows(sessions)
    assert rows[TOTP_SECRET].value == secret and rows[TOTP_STEP].value.isdigit()
    wrong = str((int(totp.code(secret, time.time())) + 1) % 1000000).zfill(6)
    _post(client, "/settings/totp/off", code=wrong)
    assert "Wrong code." in client.get("/settings").text and _rows(sessions)[TOTP_SECRET] is not None
    # the step of the "on" code is used: the next step gives a new code
    _post(client, "/settings/totp/off", code=totp.code(secret, time.time() + 30))
    assert all(v is None for v in _rows(sessions).values())
    assert "Turn on" in _card(client.get("/settings").text)


def test_on_and_off_log_out_the_other_sessions(client, sessions):
    other = TestClient(app)
    _login(other)
    secret = _turn_on(client)
    assert other.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 200
    _login(other)
    _post(client, "/settings/totp/off", code=totp.code(secret, time.time() + 30))
    assert other.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 200


def test_the_export_has_no_secret(client):
    secret = _turn_on(client)
    text = client.get("/settings/export.json").text
    assert "totp_" not in text and secret not in text


def test_no_login_and_csrf(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    anon = TestClient(app)
    for path in ("/settings/totp/start", "/settings/totp/on", "/settings/totp/off"):
        r = anon.post(path, data={"code": "123456"}, follow_redirects=False)
        assert r.status_code in (303, 403) and r.status_code != 200
    c = TestClient(app)
    _login(c)
    assert c.post("/settings/totp/start", follow_redirects=False).status_code == 403
    _start(c)
    card = _card(c.get("/settings").text)
    assert card.count('name="csrf_token"') >= 1
