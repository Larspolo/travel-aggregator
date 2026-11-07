"""The limit of the failed logins (#145): per address, for all addresses, 429 with Retry-After, the log."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.auth import login_limiter, make_password_hash
from app.main import app

PASSWORD = "correct horse"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(login_limiter, "clock", c)
    return c


def _client(address, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    return TestClient(app, client=(address, 50000))


def _login(client, password):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login").text).group(1)
    return client.post("/login", data={"password": password, "csrf_token": token}, follow_redirects=False)


def test_address_lock(monkeypatch, sessions, clock):
    c = _client("1.2.3.4", monkeypatch)
    for _ in range(5):
        assert _login(c, "wrong").status_code == 401
    r = _login(c, PASSWORD)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) == 900
    assert "Too many attempts. Try again in 15 minutes." in r.text
    assert _login(_client("5.6.7.8", monkeypatch), PASSWORD).status_code == 303
    clock.now += 15 * 60
    assert _login(c, PASSWORD).status_code == 303


def test_global_lock(monkeypatch, sessions, clock):
    for i in range(20):
        assert _login(_client(f"10.0.0.{i}", monkeypatch), "wrong").status_code == 401
    assert _login(_client("10.0.1.1", monkeypatch), PASSWORD).status_code == 429
    clock.now += 15 * 60
    assert _login(_client("10.0.1.1", monkeypatch), PASSWORD).status_code == 303


def test_success_resets_count(monkeypatch, sessions, clock):
    c = _client("1.2.3.4", monkeypatch)
    for _ in range(4):
        _login(c, "wrong")
    assert _login(c, PASSWORD).status_code == 303
    c = _client("1.2.3.4", monkeypatch)
    for _ in range(4):
        assert _login(c, "wrong").status_code == 401
    assert _login(c, PASSWORD).status_code == 303


def test_failed_login_log(monkeypatch, sessions, clock, caplog):
    c = _client("1.2.3.4", monkeypatch)
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        _login(c, "secret-guess")
    lines = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(lines) == 1
    assert "1.2.3.4" in lines[0].getMessage()
    assert "secret-guess" not in caplog.text
