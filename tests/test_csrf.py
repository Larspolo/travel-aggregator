"""CSRF tokens of the web forms (#20)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app

PASSWORD = "correct horse"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    return TestClient(app)


def token(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login").text).group(1)


def test_no_token_is_403(client):
    client.get("/login")
    r = client.post("/login", data={"password": PASSWORD}, follow_redirects=False)
    assert r.status_code == 403


def test_wrong_token_is_403(client):
    token(client)
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": "x"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/login", data={"password": PASSWORD}, headers={"X-CSRF-Token": "x"}, follow_redirects=False)
    assert r.status_code == 403


def test_no_session_is_403(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": "x"}, follow_redirects=False)
    assert r.status_code == 403


def test_session_token_works(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": token(client)}, follow_redirects=False)
    assert r.status_code == 303


def test_header_token_works(client):
    r = client.post("/login", data={"password": PASSWORD}, headers={"X-CSRF-Token": token(client)},
                    follow_redirects=False)
    assert r.status_code == 303


def test_hx_headers_on_body(client):
    t = token(client)
    assert f'"X-CSRF-Token": "{t}"' in client.get("/login").text


def test_token_changes_after_logout_and_login(client):
    first = token(client)
    client.post("/login", data={"password": PASSWORD, "csrf_token": first}, follow_redirects=False)
    client.get("/logout", follow_redirects=False)
    second = token(client)
    assert second != first
    client.post("/login", data={"password": PASSWORD, "csrf_token": second}, follow_redirects=False)
    assert token(client) != second


def test_api_post_not_affected(client):
    r = client.post("/api/health")
    assert r.status_code != 403
