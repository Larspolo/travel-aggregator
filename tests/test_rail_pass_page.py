"""The settings page "Rail passes" and the table `rail_passes` (#2265)."""

import re
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from app.auth import make_password_hash
from app.main import app
from app.models import RailPass

PASSWORD = "pw"


def _token(c, path="/passes"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _rows(sessions):
    with sessions() as s:
        return [(r.id, r.name, r.first_day.isoformat(), r.last_day.isoformat(), r.day_cost, r.carriers)
                for r in s.scalars(select(RailPass).order_by(RailPass.id))]


def _save(c, name="Interrail", first="2026-12-01", last="2026-12-31", cost="40.00", carriers="", id=""):
    return c.post("/passes", data={"id": id, "name": name, "first_day": first, "last_day": last,
                                   "day_cost": cost, "carriers": carriers, "csrf_token": _token(c)})


def test_needs_login(sessions):
    assert TestClient(app).get("/passes", follow_redirects=False).status_code in (303, 401)


def test_add_change_delete(client, sessions):
    assert "No passes" in client.get("/passes").text
    assert _save(client, carriers="  NS, DB ").status_code == 200
    rows = _rows(sessions)
    assert len(rows) == 1 and rows[0][4] == Decimal("40.00") and rows[0][5] == "NS, DB"
    assert "Interrail" in client.get("/passes").text
    pid = rows[0][0]
    _save(client, cost="35", id=str(pid))
    assert _rows(sessions)[0][4] == Decimal("35.00")
    assert "€35.00" in client.get("/passes").text
    client.post(f"/passes/{pid}/delete", data={"csrf_token": _token(client)})
    assert _rows(sessions) == []


@pytest.mark.parametrize("kw", [{"first": "2026-12-31", "last": "2026-12-01"}, {"cost": "-1"}, {"cost": "1.234"},
                                {"name": ""}, {"name": "x" * 101}, {"first": "nope"}, {"cost": "1001"}])
def test_bad_values_give_422(client, sessions, kw):
    r = _save(client, **kw)
    assert r.status_code == 422 and 'role="alert"' in r.text
    assert _rows(sessions) == []


def test_same_name_gives_422(client, sessions):
    _save(client)
    before = _rows(sessions)
    assert _save(client, cost="10").status_code == 422
    assert _rows(sessions) == before
    _save(client, name="Other")
    assert _save(client, name="Interrail", id=str(_rows(sessions)[1][0])).status_code == 422
    assert len(_rows(sessions)) == 2


def test_the_menu_links_the_page(client):
    assert 'href="/passes"' in client.get("/fees").text


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0055")
    engine = create_engine(empty_database_url)
    try:
        assert "rail_passes" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0054")
        assert "rail_passes" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "0055")
        assert "rail_passes" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
