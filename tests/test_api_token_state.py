"""GET /api/token: the state of the API token (#2047)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import token_limiter
from app.main import app
from app.models import ApiToken


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    token_limiter.reset()
    c = Clock()
    monkeypatch.setattr(token_limiter, "clock", c)
    yield c
    token_limiter.reset()


@pytest.fixture
def client(sessions):
    return TestClient(app, client=("198.51.100.8", 50000))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_without_end_date(sessions, client, clock):
    with sessions() as s:
        token = tokens.create(s, "laptop")
    r = client.get("/api/token", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"name": "laptop", "expires_at": None}


def test_valid_token_with_end_date(sessions, client, clock):
    end = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)
    with sessions() as s:
        token = tokens.create(s, "phone", expires_at=end)
    r = client.get("/api/token", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"name": "phone", "expires_at": end.isoformat()}


def test_revoked_token_is_401(sessions, client, clock):
    with sessions() as s:
        token = tokens.create(s, "old")
        token_id = s.scalar(select(ApiToken.id).where(ApiToken.name == "old"))
        tokens.revoke(s, token_id)
    r = client.get("/api/token", headers=_auth(token))
    assert r.status_code == 401
    assert r.json()["detail"] == "token revoked"
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_is_401(sessions, client, clock):
    with sessions() as s:
        token = tokens.create(s, "gone", expires_at=datetime.now(UTC) - timedelta(days=1))
    r = client.get("/api/token", headers=_auth(token))
    assert r.status_code == 401
    assert r.json()["detail"] == "token expired"
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_unknown_token_is_401(client, clock):
    r = client.get("/api/token", headers=_auth("not-a-real-token"))
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid or missing API token"
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_missing_token_is_401(client, clock):
    r = client.get("/api/token")
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid or missing API token"


def test_bad_tokens_then_429_with_retry_after(sessions, client, clock):
    with sessions() as s:
        token = tokens.create(s, "laptop")
    for _ in range(token_limiter.ADDRESS_MAX):
        assert client.get("/api/token", headers=_auth("not-a-real-token")).status_code == 401
    r = client.get("/api/token", headers=_auth(token))
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
