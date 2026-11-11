"""The days off in the settings export and its import (#2372)."""

import copy
import json
import re
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import DayOff

PASSWORD = "pw"
NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
OFF = {"first_day": "2026-12-24", "last_day": "2026-12-31", "note": "Christmas"}
FILE = {"format": "travel-aggregator-settings", "version": 1, "exported_at": "2026-11-11T00:00:00+00:00",
        "days_off": [OFF]}


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


def _days_off(sessions):
    with sessions() as s:
        return sorted((d.first_day, d.last_day, d.note) for d in s.scalars(select(DayOff)))


def test_the_export_has_each_day_off_with_its_three_fields(client, sessions):
    with sessions() as s:
        s.add(DayOff(first_day=date(2026, 12, 24), last_day=date(2026, 12, 31), note="Christmas", updated_at=NOW))
        s.commit()
    assert client.get("/settings/export.json").json()["days_off"] == [OFF]


def test_the_import_into_an_empty_database_makes_the_same_days_off(client, sessions):
    assert _days_off(sessions) == []
    assert _post(client, FILE).status_code == 200
    assert _days_off(sessions) == [(date(2026, 12, 24), date(2026, 12, 31), "Christmas")]


def test_an_import_of_the_same_file_twice_gives_no_second_row(client, sessions):
    assert _post(client, FILE).status_code == 200
    assert _post(client, FILE).status_code == 200
    assert _days_off(sessions) == [(date(2026, 12, 24), date(2026, 12, 31), "Christmas")]


def test_an_old_file_without_days_off_keeps_the_days_off(client, sessions):
    with sessions() as s:
        s.add(DayOff(first_day=date(2026, 12, 24), last_day=date(2026, 12, 31), note="Christmas", updated_at=NOW))
        s.commit()
    old = {k: v for k, v in FILE.items() if k != "days_off"}
    assert _post(client, old).status_code == 200
    assert _days_off(sessions) == [(date(2026, 12, 24), date(2026, 12, 31), "Christmas")]


def test_a_last_day_before_the_first_day_gives_an_error_and_no_change(client, sessions):
    bad = copy.deepcopy(FILE)
    bad["days_off"] = [dict(OFF, last_day="2026-12-01")]
    bad["passes"] = []
    r = _post(client, bad)
    assert r.status_code == 400
    assert "Day off 1" in r.text
    assert _days_off(sessions) == []
