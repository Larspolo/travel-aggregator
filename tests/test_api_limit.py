"""The limit of the API requests per token (#411): 120 in 60 seconds, 429 with Retry-After, the log."""

import logging

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import api_limiter
from app.main import app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    api_limiter.reset()
    c = Clock()
    monkeypatch.setattr(api_limiter, "clock", c)
    yield c
    api_limiter.reset()


@pytest.fixture
def client(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        token_b = tokens.create(s, "test-b")
    return TestClient(app), {"Authorization": f"Bearer {token}"}, {"Authorization": f"Bearer {token_b}"}


def _get(c, auth):
    return c.get("/api/trips", headers=auth)


def test_121st_request_gets_429_with_retry_after(client, clock):
    c, auth, _ = client
    for _ in range(api_limiter.MAX):
        assert _get(c, auth).status_code == 200
    r = _get(c, auth)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_limit_is_lifted_after_the_window(client, clock):
    c, auth, _ = client
    for _ in range(api_limiter.MAX):
        _get(c, auth)
    assert _get(c, auth).status_code == 429
    clock.now += api_limiter.WINDOW
    assert _get(c, auth).status_code == 200


def test_second_token_is_not_limited(client, clock):
    c, auth, auth_b = client
    for _ in range(api_limiter.MAX):
        _get(c, auth)
    assert _get(c, auth).status_code == 429
    assert _get(c, auth_b).status_code == 200


def test_429_log_names_token_id_not_token(client, clock, caplog):
    c, auth, _ = client
    token_value = auth["Authorization"].removeprefix("Bearer ")
    for _ in range(api_limiter.MAX):
        _get(c, auth)
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        assert _get(c, auth).status_code == 429
    messages = [r.getMessage() for r in caplog.records if r.name == "app.auth"]
    assert len(messages) == 1
    assert "token" in messages[0]
    assert token_value not in messages[0]
