"""The log of the login attempts (#1353)."""

import time

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select

from app import login_log, totp
from app.auth import TOTP_SECRET, TOTP_STEP, login_limiter, make_password_hash, require_login
from app.main import app
from app.models import LoginEvent, Setting
from tests.test_totp_login import _code, _csrf, _password
from tests.test_trip_booked import _alembic

PASSWORD = "correct horse"
AGENT = "TestBrowser/1.0"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    login_limiter.reset()
    yield TestClient(app, headers={"User-Agent": AGENT})
    login_limiter.reset()


def _rows(sessions):
    with sessions() as s:
        return [(e.result, e.address, e.user_agent) for e in s.scalars(select(LoginEvent).order_by(LoginEvent.id))]


def _post(client, password):
    return client.post("/login", data={"password": password, "csrf_token": _csrf(client)}, follow_redirects=False)


def test_a_wrong_and_a_good_password_give_two_rows(client, sessions):
    assert _post(client, "wrong").status_code == 401
    assert _post(client, PASSWORD).status_code == 303
    assert _rows(sessions) == [("failed", "testclient", AGENT), ("ok", "testclient", AGENT)]


def test_the_second_step_records_the_code_results(client, sessions):
    secret = totp.new_secret()
    with sessions() as s:
        s.merge(Setting(key=TOTP_SECRET, value=secret))
        s.merge(Setting(key=TOTP_STEP, value="-1"))
        s.commit()
    _password(client)
    good = totp.code(secret, time.time())
    assert _code(client, "000000" if good != "000000" else "111111").status_code == 401
    assert _code(client, good).status_code == 303
    assert [r[0] for r in _rows(sessions)] == ["code-failed", "code"]


def test_a_recovery_code_records_recovery(client, sessions, monkeypatch):
    from app import recovery
    monkeypatch.setattr(recovery, "use", lambda session, code: code == "abcdefgh")
    with sessions() as s:
        s.merge(Setting(key=TOTP_SECRET, value=totp.new_secret()))
        s.commit()
    _password(client)
    assert _code(client, "abcdefgh").status_code == 303
    assert [r[0] for r in _rows(sessions)] == ["recovery"]


def test_the_log_keeps_the_newest_200(client, sessions):
    from starlette.requests import Request
    req = Request({"type": "http", "headers": [(b"user-agent", b"x" * 400)], "client": ("1.2.3.4", 1)})
    with sessions() as s:
        for i in range(205):
            login_log.record(s, req, f"r{i}")
        s.commit()
        assert s.scalar(select(func.count()).select_from(LoginEvent)) == 200
        rows = login_log.recent(s)
        assert [r.result for r in rows] == [f"r{i}" for i in range(204, 184, -1)]
        assert len(rows[0].user_agent) == 300


def test_the_export_has_no_login_rows(client, sessions):
    _post(client, "wrong")
    app.dependency_overrides[require_login] = lambda: None
    try:
        text = TestClient(app).get("/settings/export.json").text
    finally:
        app.dependency_overrides.pop(require_login, None)
    assert "testclient" not in text and AGENT not in text and "login_events" not in text


def test_migration_0028_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "login_events" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0027")
        assert "login_events" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "0028")
        assert "login_events" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
