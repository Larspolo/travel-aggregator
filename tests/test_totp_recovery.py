"""The one-time recovery codes of the second login step, for a lost phone (#1316)."""

import hashlib
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import totp
from app.auth import TOTP_RECOVERY, TOTP_SECRET, TOTP_STEP, login_limiter, make_password_hash
from app.main import app
from app.models import Setting

PASSWORD = "correct horse"
CODE_RE = re.compile(r'<li><code>([a-z2-9]{5}-[a-z2-9]{5})</code></li>')


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    login_limiter.reset()
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


def _row(sessions, key):
    with sessions() as s:
        row = s.get(Setting, key)
        return row.value if row else None


def _turn_on(client, at=None):
    """Turn the step on and return (secret, the ten codes that the settings page shows once)."""
    assert _post(client, "/settings/totp/start").status_code == 303
    page = client.get("/settings").text
    secret = re.search(r'class="totp-key">([A-Z2-7 ]+)<', page).group(1).replace(" ", "")
    now = time.time() if at is None else at
    assert _post(client, "/settings/totp/on", code=totp.code(secret, now)).status_code == 303
    return secret, _codes(client)


def _codes(client):
    return [c.replace("-", "") for c in CODE_RE.findall(client.get("/settings").text)]


def _login_code(client, code):
    """Log in with the password, then send `code` at the code page. Returns the response."""
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.headers["location"] == "/login/code"
    return client.post("/login/code", data={"code": code, "csrf_token": _csrf(client, "/login/code")},
                       follow_redirects=False)


def _logged_in(client):
    r = client.get("/", follow_redirects=False)
    return r.status_code == 200


def test_turn_on_shows_ten_codes_once_and_stores_digests(client, sessions):
    _, codes = _turn_on(client)
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(c) == 10 for c in codes)
    assert "Recovery codes left: 10" in client.get("/settings").text
    # the next page view does not show them again
    assert _codes(client) == []
    stored = _row(sessions, TOTP_RECOVERY)
    digests = json.loads(stored)
    assert len(digests) == 10
    assert all(len(d) == 64 for d in digests)
    assert digests == [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    assert not any(c in stored for c in codes)


def test_recovery_code_logs_in_one_time(client, sessions):
    _, codes = _turn_on(client)
    other = TestClient(app)
    typed = codes[0][:5].upper() + codes[0][5:]  # upper case, no dash
    assert _login_code(other, typed).status_code == 303
    assert _logged_in(other)
    again = TestClient(app)
    r = _login_code(again, codes[0])
    assert r.status_code == 401 and "Wrong code." in r.text
    assert not _logged_in(again)
    assert "Recovery codes left: 9" in client.get("/settings").text
    assert len(json.loads(_row(sessions, TOTP_RECOVERY))) == 9


def test_recovery_code_with_dash_and_no_case_works(client):
    _, codes = _turn_on(client)
    other = TestClient(app)
    code = codes[1]
    typed = f"{code[:5]}-{code[5:]}".upper()
    assert _login_code(other, typed).status_code == 303
    assert _logged_in(other)


def test_new_codes_need_an_app_code_and_replace_the_old(client, sessions):
    secret, old = _turn_on(client)
    r = _post(client, "/settings/totp/recovery", code="000000x")
    assert r.status_code == 303
    page = client.get("/settings").text
    assert "Wrong code." in page and CODE_RE.findall(page) == []
    # the step of the "on" code is used: a code of the next step is needed
    _post(client, "/settings/totp/recovery", code=totp.code(secret, time.time() + 30))
    new = _codes(client)
    assert len(new) == 10 and set(new).isdisjoint(old)
    assert len(json.loads(_row(sessions, TOTP_RECOVERY))) == 10
    anon = TestClient(app)
    assert _login_code(anon, old[0]).status_code == 401
    assert not _logged_in(anon)
    ok = TestClient(app)
    assert _login_code(ok, new[0]).status_code == 303
    assert _logged_in(ok)


def test_turn_off_deletes_the_codes_and_the_export_has_no_totp_key(client, sessions):
    secret, _ = _turn_on(client)
    assert _row(sessions, TOTP_RECOVERY) is not None
    _post(client, "/settings/totp/off", code=totp.code(secret, time.time() + 30))
    assert _row(sessions, TOTP_RECOVERY) is None
    assert _row(sessions, TOTP_SECRET) is None and _row(sessions, TOTP_STEP) is None
    assert "totp_" not in client.get("/settings/export.json").text


def test_the_code_page_takes_the_long_form(client):
    _turn_on(client)
    anon = TestClient(app)
    r = anon.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(anon)}, follow_redirects=False)
    assert r.headers["location"] == "/login/code"
    assert 'maxlength="11"' in anon.get("/login/code").text
