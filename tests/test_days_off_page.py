"""The settings page "Days off" and the table `days_off` (#2370)."""

import re

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from app.auth import make_password_hash
from app.main import app
from app.models import DayOff

PASSWORD = "pw"


def _token(c, path="/days-off"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _rows(sessions):
    with sessions() as s:
        return [(r.id, r.first_day.isoformat(), r.last_day.isoformat(), r.note)
                for r in s.scalars(select(DayOff).order_by(DayOff.first_day))]


def _save(c, first="2026-12-24", last="", note="", id=""):
    return c.post("/days-off", data={"id": id, "first_day": first, "last_day": last, "note": note,
                                     "csrf_token": _token(c)})


def test_needs_login(sessions):
    assert TestClient(app).get("/days-off", follow_redirects=False).status_code in (303, 401)


def test_add_change_delete(client, sessions):
    assert "No days off. With no days off, the costs do not change." in client.get("/days-off").text
    assert _save(client).status_code == 200
    assert _save(client, "2026-12-28", "2026-12-31", " Vacation ").status_code == 200
    rows = _rows(sessions)
    assert [r[1:] for r in rows] == [("2026-12-24", "2026-12-24", ""), ("2026-12-28", "2026-12-31", "Vacation")]
    page = client.get("/days-off").text
    assert "2026-12-28 – 2026-12-31" in page and "Vacation" in page
    assert page.index("2026-12-24") < page.index("2026-12-28")
    _save(client, "2026-12-28", "2027-01-02", "Vacation", id=str(rows[1][0]))
    assert _rows(sessions)[1][1:] == ("2026-12-28", "2027-01-02", "Vacation")
    assert "2026-12-28 – 2027-01-02" in client.get("/days-off").text
    client.post(f"/days-off/{rows[0][0]}/delete", data={"csrf_token": _token(client)})
    assert [r[1] for r in _rows(sessions)] == ["2026-12-28"]
    assert "2026-12-24" not in client.get("/days-off").text


@pytest.mark.parametrize("kw", [{"first": "nope"}, {"first": "2026-12-31", "last": "2026-12-01"},
                                {"note": "x" * 101}, {"first": ""}])
def test_bad_values_give_422(client, sessions, kw):
    r = _save(client, **kw)
    assert r.status_code == 422 and 'role="alert"' in r.text
    assert _rows(sessions) == []


def test_the_note_is_escaped(client, sessions):
    _save(client, note="<b>x</b>")
    assert "<b>x</b>" not in client.get("/days-off").text


def test_the_menu_links_the_page(client):
    assert 'href="/days-off"' in client.get("/passes").text


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0060")
    engine = create_engine(empty_database_url)
    try:
        assert "days_off" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0058")
        assert "days_off" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "0060")
        assert "days_off" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
