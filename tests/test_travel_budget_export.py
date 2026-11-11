"""The travel budgets in the settings export and its import (#2377)."""

import copy
import json
import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import TravelBudget

PASSWORD = "pw"
NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
BUDGETS = [{"year": 2026, "amount": "1200.00"}, {"year": 2027, "amount": "800.00"}]
FILE = {"format": "travel-aggregator-settings", "version": 1, "exported_at": "2026-11-11T00:00:00+00:00",
        "travel_budgets": BUDGETS}


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


def _budgets(sessions):
    with sessions() as s:
        return sorted((b.year, b.amount) for b in s.scalars(select(TravelBudget)))


def test_the_export_has_each_budget_with_its_year_and_amount(client, sessions):
    with sessions() as s:
        s.add(TravelBudget(year=2026, amount=Decimal("1200.00"), updated_at=NOW))
        s.add(TravelBudget(year=2027, amount=Decimal("800"), updated_at=NOW))
        s.commit()
    data = client.get("/settings/export.json").json()
    assert data["travel_budgets"] == [{"year": 2026, "amount": "1200.00"}, {"year": 2027, "amount": "800.00"}]


def test_the_import_makes_the_budgets_in_an_empty_database(client, sessions):
    assert _budgets(sessions) == []
    r = _post(client, FILE)
    assert r.status_code == 200
    assert _budgets(sessions) == [(2026, Decimal("1200.00")), (2027, Decimal("800"))]


def test_a_second_import_gives_no_second_row(client, sessions):
    _post(client, FILE)
    _post(client, FILE)
    assert len(_budgets(sessions)) == 2


def test_an_import_changes_the_amount_of_a_year_and_keeps_the_others(client, sessions):
    with sessions() as s:
        s.add(TravelBudget(year=2026, amount=Decimal("100"), updated_at=NOW))
        s.add(TravelBudget(year=2025, amount=Decimal("50"), updated_at=NOW))
        s.commit()
    _post(client, FILE)
    assert _budgets(sessions) == [(2025, Decimal("50")), (2026, Decimal("1200.00")), (2027, Decimal("800"))]


def test_an_old_file_without_budgets_keeps_the_budgets(client, sessions):
    with sessions() as s:
        s.add(TravelBudget(year=2026, amount=Decimal("100"), updated_at=NOW))
        s.commit()
    old = {k: v for k, v in FILE.items() if k != "travel_budgets"}
    r = _post(client, old)
    assert r.status_code == 200
    assert _budgets(sessions) == [(2026, Decimal("100"))]


@pytest.mark.parametrize("bad", [
    {"year": 2026, "amount": "-5"},
    {"year": 1999, "amount": "10"},
    {"year": 2026, "amount": "10.001"},
    {"year": 2026, "amount": 10.5},
])
def test_a_bad_budget_gives_an_error_and_changes_nothing(client, sessions, bad):
    with sessions() as s:
        s.add(TravelBudget(year=2026, amount=Decimal("100"), updated_at=NOW))
        s.commit()
    body = copy.deepcopy(FILE)
    body["travel_budgets"] = [{"year": 2030, "amount": "70"}, bad]
    r = _post(client, body)
    assert r.status_code == 400
    assert "Travel budget 2" in r.text
    assert _budgets(sessions) == [(2026, Decimal("100"))]


def test_two_budgets_for_the_same_year_give_an_error(client, sessions):
    body = copy.deepcopy(FILE)
    body["travel_budgets"] = [{"year": 2026, "amount": "1"}, {"year": 2026, "amount": "2"}]
    r = _post(client, body)
    assert r.status_code == 400
    assert _budgets(sessions) == []
