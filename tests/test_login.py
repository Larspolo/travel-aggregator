"""The owner login (#19): the session cookie, the redirects and the API without login."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import check_password, make_password_hash
from app.main import app

PASSWORD = "correct horse"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    return TestClient(app)


def _token(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login").text).group(1)


def test_hash_check():
    stored = make_password_hash(PASSWORD, iterations=1000)
    assert check_password(PASSWORD, stored)
    assert not check_password("wrong", stored)
    assert not check_password(PASSWORD, "")
    assert not check_password(PASSWORD, "garbage$x$y$z")


def test_index_needs_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_logout(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _token(client)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/", follow_redirects=False).status_code == 200
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


def test_wrong_password(client):
    r = client.post("/login", data={"password": "wrong", "csrf_token": _token(client)}, follow_redirects=False)
    assert r.status_code == 401
    assert "Wrong password" in r.text and 'name="password"' in r.text
    assert "pbkdf2" not in r.text
    assert client.get("/", follow_redirects=False).status_code == 303


def test_health_needs_no_login(client):
    assert client.get("/api/health", follow_redirects=False).status_code != 303
