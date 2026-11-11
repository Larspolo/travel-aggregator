"""The API tokens page marks a token with no use for 90 days (#1845)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_token, make_password_hash
from app.main import app
from app.models import ApiToken

PASSWORD = "pw"
MARK = "not used for 90 days"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _add(sessions, name, created_days_ago, used_days_ago=None, revoked=False):
    now = datetime.now(timezone.utc)
    with sessions() as s:
        s.add(ApiToken(
            name=name,
            token_hash=hash_token(name),
            created_at=now - timedelta(days=created_days_ago),
            last_used_at=None if used_days_ago is None else now - timedelta(days=used_days_ago),
            revoked_at=now if revoked else None,
        ))
        s.commit()


def _row(text, name):
    return re.search(rf"<tr>\s*<td>{name}</td>.*?</tr>", text, re.S).group(0)


def test_used_91_days_ago_is_marked_and_89_days_ago_is_not(sessions, client):
    _add(sessions, "old", created_days_ago=200, used_days_ago=91)
    _add(sessions, "recent", created_days_ago=200, used_days_ago=89)
    page = client.get("/tokens").text
    assert MARK in _row(page, "old")
    assert MARK not in _row(page, "recent")


def test_never_used_and_created_91_days_ago_is_marked(sessions, client):
    _add(sessions, "idle", created_days_ago=91)
    _add(sessions, "fresh", created_days_ago=10)
    page = client.get("/tokens").text
    assert MARK in _row(page, "idle")
    assert MARK not in _row(page, "fresh")


def test_revoked_token_is_never_marked(sessions, client):
    _add(sessions, "gone", created_days_ago=200, used_days_ago=200, revoked=True)
    page = client.get("/tokens").text
    assert MARK not in _row(page, "gone")
    assert "revoked" in _row(page, "gone")
