"""The rail passes in the settings export and its import (#2268)."""

import copy
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import RailPass

PASSWORD = "pw"
NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
PASS = {"name": "Interrail", "first_day": "2026-12-01", "last_day": "2026-12-31", "day_cost": "40.00",
        "carriers": "DB, SBB"}
FILE = {"format": "travel-aggregator-settings", "version": 1, "exported_at": "2026-11-11T00:00:00+00:00",
        "passes": [PASS]}


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _post(c, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return c.post("/settings/import", data={"csrf_token": _token(c, "/settings/import")},
                  files={"file": ("s.json", raw, "application/json")})


def _passes(sessions):
    with sessions() as s:
        return sorted((p.name, p.first_day, p.last_day, p.day_cost, p.carriers) for p in s.scalars(select(RailPass)))


def test_the_export_has_the_pass_with_its_five_fields(client, sessions):
    with sessions() as s:
        s.add(RailPass(name="Interrail", first_day=date(2026, 12, 1), last_day=date(2026, 12, 31),
                       day_cost=Decimal("40.00"), carriers="DB, SBB", updated_at=NOW))
        s.commit()
    data = client.get("/settings/export.json").json()
    assert data["passes"] == [PASS]


def test_the_import_makes_the_pass_in_an_empty_database(client, sessions):
    assert _passes(sessions) == []
    r = _post(client, FILE)
    assert r.status_code == 200
    assert _passes(sessions) == [("Interrail", date(2026, 12, 1), date(2026, 12, 31), Decimal("40.00"), "DB, SBB")]


def test_the_import_changes_a_pass_with_the_same_name(client, sessions):
    with sessions() as s:
        s.add(RailPass(name="Interrail", first_day=date(2026, 6, 1), last_day=date(2026, 6, 7),
                       day_cost=Decimal("10"), carriers="", updated_at=NOW))
        s.commit()
    assert _post(client, FILE).status_code == 200
    assert _passes(sessions) == [("Interrail", date(2026, 12, 1), date(2026, 12, 31), Decimal("40.00"), "DB, SBB")]


def test_an_old_file_without_passes_keeps_the_passes(client, sessions):
    with sessions() as s:
        s.add(RailPass(name="Interrail", first_day=date(2026, 12, 1), last_day=date(2026, 12, 31),
                       day_cost=Decimal("40.00"), carriers="", updated_at=NOW))
        s.commit()
    old = {k: v for k, v in FILE.items() if k != "passes"}
    assert _post(client, old).status_code == 200
    assert _passes(sessions) == [("Interrail", date(2026, 12, 1), date(2026, 12, 31), Decimal("40.00"), "")]


def test_a_last_day_before_the_first_day_gives_an_error_and_no_change(client, sessions):
    with sessions() as s:
        s.add(RailPass(name="Old", first_day=date(2026, 1, 1), last_day=date(2026, 1, 5),
                       day_cost=Decimal("5"), carriers="", updated_at=NOW))
        s.commit()
    bad = copy.deepcopy(FILE)
    bad["passes"] = [dict(PASS, last_day="2026-11-30")]
    r = _post(client, bad)
    assert r.status_code == 400
    assert _passes(sessions) == [("Old", date(2026, 1, 1), date(2026, 1, 5), Decimal("5"), "")]
