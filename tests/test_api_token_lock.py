"""The limit of the bad API tokens per address (#412): 20 in 15 minutes, 429 with Retry-After for 15 minutes."""

import logging

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import token_limiter
from app.main import app


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
    with sessions() as s:
        token = tokens.create(s, "test")
    return TestClient(app, client=("198.51.100.7", 50000)), {"Authorization": f"Bearer {token}"}


def _other(client_addr):
    return TestClient(app, client=(client_addr, 50000))


BAD = {"Authorization": "Bearer not-a-real-token"}


def _get(c, auth):
    return c.get("/api/trips", headers=auth)


def test_19_bad_tokens_get_401(client, clock):
    c, _ = client
    for _ in range(token_limiter.ADDRESS_MAX - 1):
        assert _get(c, BAD).status_code == 401


def test_20th_bad_token_is_401_then_429_even_with_valid_token(client, clock):
    c, good = client
    for _ in range(token_limiter.ADDRESS_MAX):
        assert _get(c, BAD).status_code == 401
    r = _get(c, BAD)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    r = _get(c, good)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_missing_token_counts_as_bad(client, clock):
    c, _ = client
    for _ in range(token_limiter.ADDRESS_MAX):
        assert _get(c, {}).status_code == 401
    assert _get(c, {}).status_code == 429


def test_other_address_is_not_locked(client, clock):
    c, good = client
    for _ in range(token_limiter.ADDRESS_MAX):
        _get(c, BAD)
    assert _get(c, good).status_code == 429
    other = _other("203.0.113.9")
    assert _get(other, BAD).status_code == 401
    assert _get(other, good).status_code == 200


def test_lock_is_lifted_after_15_minutes(client, clock):
    c, good = client
    for _ in range(token_limiter.ADDRESS_MAX):
        _get(c, BAD)
    assert _get(c, good).status_code == 429
    clock.now += token_limiter.LOCK
    assert _get(c, good).status_code == 200


def test_bad_tokens_older_than_the_window_do_not_count(client, clock):
    c, good = client
    for _ in range(token_limiter.ADDRESS_MAX - 1):
        _get(c, BAD)
    clock.now += token_limiter.WINDOW
    _get(c, BAD)
    assert _get(c, good).status_code == 200


def test_log_names_the_address_not_the_token(client, clock, caplog):
    c, _ = client
    caplog.set_level(logging.WARNING)
    for _ in range(token_limiter.ADDRESS_MAX):
        _get(c, BAD)
    text = caplog.text
    assert "bad API token from 198.51.100.7" in text
    assert "not-a-real-token" not in text
