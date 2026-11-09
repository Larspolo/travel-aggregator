"""The one-time code after the password at the login (#1315)."""

import re
import time

import pytest
from fastapi.testclient import TestClient

from app import totp
from app.auth import TOTP_SECRET, TOTP_STEP, login_limiter, make_password_hash
from app.main import app
from app.models import Setting
from app.web import pages

PASSWORD = "correct horse"
SECRET = totp.new_secret()


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    login_limiter.failures.clear()
    login_limiter.locked_until.clear()
    login_limiter.all_failures.clear()
    login_limiter.global_locked_until = 0.0
    with sessions() as s:
        s.merge(Setting(key=TOTP_SECRET, value=SECRET))
        s.merge(Setting(key=TOTP_STEP, value="-1"))
        s.commit()
    yield TestClient(app)
    login_limiter.failures.clear()
    login_limiter.locked_until.clear()
    login_limiter.global_locked_until = 0.0


def _csrf(client, path="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _password(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login/code"


def _code(client, code):
    return client.post("/login/code", data={"code": code, "csrf_token": _csrf(client, "/login/code")},
                       follow_redirects=False)


def _logged_in(client):
    r = client.get("/", follow_redirects=False)
    return not (r.status_code in (302, 303, 307) and "/login" in r.headers.get("location", ""))


def _wrong(code):
    return "000000" if code != "000000" else "111111"


def test_password_alone_does_not_log_in(client):
    _password(client)
    page = client.get("/login/code").text
    assert 'autocomplete="one-time-code"' in page and 'inputmode="numeric"' in page
    assert not _logged_in(client)


def test_correct_code_logs_in_once(client):
    _password(client)
    code = totp.code(SECRET, time.time())
    r = _code(client, code)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert _logged_in(client)
    other = TestClient(app)
    _password(other)
    assert _code(other, code).status_code == 401
    assert not _logged_in(other)


def test_wrong_code(client):
    _password(client)
    r = _code(client, _wrong(totp.code(SECRET, time.time())))
    assert r.status_code == 401 and "Wrong code." in r.text
    assert not _logged_in(client)


def test_code_before_the_last_step(client, sessions):
    now = time.time()
    with sessions() as s:
        s.merge(Setting(key=TOTP_STEP, value=str(int(now) // totp.STEP)))
        s.commit()
    _password(client)
    assert _code(client, totp.code(SECRET, now - totp.STEP)).status_code == 401


def test_no_password_first(client):
    assert client.get("/login/code", follow_redirects=False).headers["location"] == "/login"
    r = _code(client, totp.code(SECRET, time.time()))
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_old_pending_mark(client, monkeypatch):
    _password(client)
    csrf = _csrf(client, "/login/code")
    real = time.time
    monkeypatch.setattr(pages.clock, "time", lambda: real() + pages.TOTP_PENDING_MAX + 1)
    r = client.post("/login/code", data={"code": totp.code(SECRET, real()), "csrf_token": csrf},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_wrong_codes_count_in_the_limiter(client):
    _password(client)
    wrong = _wrong(totp.code(SECRET, time.time()))
    for _ in range(login_limiter.ADDRESS_MAX):
        assert _code(client, wrong).status_code == 401
    assert _code(client, wrong).status_code == 429


def test_api_token_with_the_step_on(client, sessions):
    from app.tokens import create
    with sessions() as s:
        plain = create(s, "test")
    assert client.get("/api/trips", headers={"Authorization": f"Bearer {plain}"}).status_code == 200
