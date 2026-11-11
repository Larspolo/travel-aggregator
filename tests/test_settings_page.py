"""The settings page with the capture retention period (#207)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.auth import make_password_hash
from app.ingest import store
from app.main import app
from app.models import Capture, Setting, Trip
from app.schemas import IngestIn

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _shown(c):
    return re.search(r'name="retention"[^>]*value="(\d+)"', c.get("/settings").text).group(1)


def _save(c, value):
    return c.post("/settings", data={"retention": value, "csrf_token": _token(c, "/settings")},
                  follow_redirects=False)


def test_no_login_redirects():
    r = TestClient(app).get("/settings", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=%2F")  # the target of #2103


def test_default_and_saved_value(client):
    assert _shown(client) == "90"
    assert 'href="/settings"' in client.get("/").text
    assert _save(client, "30").status_code == 303
    assert _shown(client) == "30"


def test_post_needs_csrf(client):
    assert client.post("/settings", data={"retention": "5"}).status_code in (400, 403)


@pytest.mark.parametrize("bad", ["-1", "3651", "abc", ""])
def test_bad_value_gets_422_and_keeps_value(client, bad):
    _save(client, "7")
    assert _save(client, bad).status_code == 422
    assert _shown(client) == "7"


def _ingest_with_old_capture(sessions, days_old):
    with sessions() as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        s.add(Capture(trip_id=trip.id, source="ns", captured_at=datetime.now(UTC) - timedelta(days=days_old)))
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        store(s, IngestIn.model_construct(trip_id=trip_id, source="ns", parser_version="1",
                                          captured_at=datetime.now(UTC), page_url=None, search_context=None,
                                          raw=None, offers=[]))
    with sessions() as s:
        return len(s.scalars(select(Capture)).all())


def test_ingest_uses_saved_value(sessions, client):
    _save(client, "10")
    assert _ingest_with_old_capture(sessions, 20) == 1  # only the new capture stays


def test_zero_keeps_all(sessions, client):
    _save(client, "0")
    assert _ingest_with_old_capture(sessions, 4000) == 2
    with sessions() as s:
        assert s.get(Setting, "capture_retention_days").value == "0"


def test_migration_up_and_down(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    from sqlalchemy import create_engine
    command.upgrade(cfg, "head")
    eng = create_engine(empty_database_url)
    assert "settings" in inspect(eng).get_table_names()
    command.downgrade(cfg, "0006")
    assert "settings" not in inspect(eng).get_table_names()
    command.upgrade(cfg, "head")
    eng.dispose()
