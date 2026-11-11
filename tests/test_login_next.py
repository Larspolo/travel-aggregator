"""The login goes back to the asked page (#2103)."""

import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app import totp
from app.auth import TOTP_SECRET, LoginRequired, TOTP_STEP, login_limiter, make_password_hash, safe_next
from app.main import app
from app.models import Setting

PASSWORD = "correct horse"
TARGET = "/trips/1?day=2026-05-03"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    login_limiter.failures.clear()
    login_limiter.locked_until.clear()
    yield TestClient(app)
    login_limiter.failures.clear()
    login_limiter.locked_until.clear()


def _login(client, login_url):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(login_url).text).group(1)
    return client.post("/login", data={"password": PASSWORD, "csrf_token": token}, follow_redirects=False)


def test_get_redirect_has_target_and_login_goes_back(client):
    r = client.get(TARGET, follow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/login?next=")
    assert parse_qs(urlsplit(location).query)["next"] == [TARGET]
    r = _login(client, location)
    assert r.status_code == 303 and r.headers["location"] == TARGET


def test_post_keeps_plain_login_redirect():
    request = Request({"type": "http", "method": "POST", "path": "/trips/1", "query_string": b"", "headers": []})
    assert LoginRequired(request).headers["Location"] == "/login"


@pytest.mark.parametrize("target", ["//evil.example/x", "https://evil.example/", "/\\evil.example", None])
def test_bad_target_goes_to_root(client, target):
    url = "/login" if target is None else "/login?" + urlencode({"next": target})
    r = _login(client, url)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_safe_next():
    assert safe_next("/a?b=1") == "/a?b=1"
    for bad in ("", None, "a", "//x", "/\\x", "/a\nb", "/" + "a" * 2000, "http://x/"):
        assert safe_next(bad) == "/"


def test_totp_step_keeps_target(client, sessions):
    secret = totp.new_secret()
    with sessions() as s:
        s.merge(Setting(key=TOTP_SECRET, value=secret))
        s.merge(Setting(key=TOTP_STEP, value="-1"))
        s.commit()
    location = client.get(TARGET, follow_redirects=False).headers["location"]
    r = _login(client, location)
    assert r.headers["location"] == "/login/code"
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login/code").text).group(1)
    r = client.post("/login/code", data={"code": totp.code(secret, time.time()), "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == TARGET
