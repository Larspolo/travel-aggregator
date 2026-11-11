"""The import of the settings file (#1207)."""

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
from app.models import AccessTime, CurrencyRate, ScoreProfile, Setting, SourceFee
from app.schemas import MAX_BODY_BYTES

PASSWORD = "pw"
NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
FILE = {
    "format": "travel-aggregator-settings", "version": 1, "exported_at": NOW.isoformat(),
    "profiles": [{"name": "Cheap", "is_default": True, "config": {"hour_markup": "5", "early_limit": "07:00"}},
                 {"name": "Fast", "is_default": False, "config": {"hour_markup": "30"}},
                 {"name": "Calm", "is_default": False, "config": {}}],
    "places": [{"place": "Home", "kind": "access", "minutes": 15, "cost": "2.50"},
               {"place": "Home", "kind": "egress", "minutes": 10, "cost": "0"}],
    "rates": [{"code": "CHF", "eur_per_unit": "1.064512"}, {"code": "GBP", "eur_per_unit": "1.17"}],
    "fees": [{"source": "bahn", "amount": "1.99"}],
    "settings": {"capture_retention_days": "30", "reminder_days": "7", "reminder_before_days": "14",
                 "source_alert_on": "0"},
}


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


def _tables(sessions):
    with sessions() as s:
        return (sorted((p.name, p.is_default, json.dumps(p.config_json, sort_keys=True))
                       for p in s.scalars(select(ScoreProfile))),
                sorted((a.place_text, a.kind, a.minutes, a.cost) for a in s.scalars(select(AccessTime))),
                sorted((r.code, r.eur_per_unit, r.updated_at) for r in s.scalars(select(CurrencyRate))),
                sorted((f.source, f.amount, f.updated_at) for f in s.scalars(select(SourceFee))),
                sorted((x.key, x.value) for x in s.scalars(select(Setting))))


def test_the_settings_page_links_the_import(client):
    assert 'href="/settings/import"' in client.get("/settings").text


def test_an_import_into_an_empty_database_makes_all_rows(client, sessions):
    r = _post(client, FILE)
    assert r.status_code == 200
    assert "3 profiles, 2 places, 2 rates, 1 fee and 4 settings imported" in r.text
    first = _tables(sessions)
    profiles, places, rates, fees, values = first
    assert [p[:2] for p in profiles] == [("Calm", False), ("Cheap", True), ("Fast", False)]
    assert ("Home", "access", 15, Decimal("2.50")) in places
    assert [x[:2] for x in rates] == [("CHF", Decimal("1.064512")), ("GBP", Decimal("1.170000"))]
    assert values == sorted(FILE["settings"].items())
    assert _post(client, FILE).status_code == 200
    assert _tables(sessions) == first


def test_the_file_wins_and_the_other_rows_stay(client, sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Fast", is_default=False, config_json={"hour_markup": "99"}))
        s.add(ScoreProfile(name="Mine", is_default=False, config_json={}))
        s.add(AccessTime(place_text="Home", kind="access", minutes=40, cost=Decimal("9")))
        s.add(AccessTime(place_text="Work", kind="access", minutes=5, cost=Decimal("0")))
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("2"), updated_at=NOW))
        s.add(CurrencyRate(code="USD", eur_per_unit=Decimal("0.9"), updated_at=NOW))
        s.add(SourceFee(source="bahn", amount=Decimal("5"), updated_at=NOW))
        s.add(SourceFee(source="flix", amount=Decimal("1"), updated_at=NOW))
        s.add(Setting(key="ntfy_url", value="https://ntfy.example/x"))
        s.commit()
    assert _post(client, FILE).status_code == 200
    with sessions() as s:
        fast = s.scalars(select(ScoreProfile).where(ScoreProfile.name == "Fast")).one()
        assert fast.config_json["hour_markup"] == "30"
        assert s.scalars(select(ScoreProfile).where(ScoreProfile.name == "Mine")).one() is not None
        home = s.scalars(select(AccessTime).where(AccessTime.place_text == "Home", AccessTime.kind == "access")).all()
        assert [(a.minutes, a.cost) for a in home] == [(15, Decimal("2.50"))]
        assert s.get(AccessTime, s.scalars(select(AccessTime.id).where(AccessTime.place_text == "Work")).one())
        assert s.get(CurrencyRate, "CHF").eur_per_unit == Decimal("1.064512")
        assert s.get(CurrencyRate, "USD").eur_per_unit == Decimal("0.9")
        assert s.get(SourceFee, "bahn").amount == Decimal("1.99") and s.get(SourceFee, "flix").amount == 1
        assert s.get(Setting, "ntfy_url").value == "https://ntfy.example/x"


def _bad(**change):
    data = copy.deepcopy(FILE)
    for key, value in change.items():
        data[key] = value
    return data


@pytest.mark.parametrize("body, text", [
    (_bad(format="other"), "not a settings export"),
    (_bad(version=2), "The version must be 1"),
    (_bad(rates=[{"code": "CHF", "eur_per_unit": "abc"}]), "Rate 1"),
    (_bad(rates=[{"code": "CHF", "eur_per_unit": "0"}]), "Rate 1"),
    (_bad(rates=[{"code": "chf", "eur_per_unit": "1"}]), "Rate 1"),
    (_bad(fees=[{"source": "bahn", "amount": "-1"}]), "Fee 1"),
    (_bad(places=[{"place": "Home", "kind": "access", "minutes": 5, "cost": "-0.01"}]), "Place 1"),
    (_bad(settings={"ntfy_url": "https://evil.example"}), "ntfy_url"),
    (_bad(settings={"reminder_days": "x"}), "reminder_days"),
    (_bad(profiles=[{"name": "A", "is_default": True, "config": {}}, {"name": "B", "is_default": True, "config": {}}]),
     "At most one profile"),
    (_bad(profiles=[{"name": "A", "config": {"hour_markup": "500"}}]), "hour_markup"),
    (b"not json", "not JSON"),
])
def test_a_bad_file_changes_no_row(client, sessions, body, text):
    assert _post(client, {**FILE, "settings": {"reminder_days": "3"}}).status_code == 200
    before = _tables(sessions)
    r = _post(client, body)
    assert r.status_code == 400 and text in r.text
    assert _tables(sessions) == before


def test_a_file_with_no_default_keeps_the_default(client, sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Mine", is_default=True, config_json={}))
        s.commit()
    data = copy.deepcopy(FILE)
    data["profiles"][0]["is_default"] = False
    assert _post(client, data).status_code == 200
    with sessions() as s:
        assert s.scalars(select(ScoreProfile.name).where(ScoreProfile.is_default.is_(True))).all() == ["Mine"]
    assert _post(client, FILE).status_code == 200
    with sessions() as s:
        assert s.scalars(select(ScoreProfile.name).where(ScoreProfile.is_default.is_(True))).all() == ["Cheap"]


def test_no_csrf_token_is_forbidden(client, sessions):
    r = client.post("/settings/import", files={"file": ("s.json", json.dumps(FILE).encode(), "application/json")})
    assert r.status_code == 403
    assert _tables(sessions)[0] == []


def test_a_file_above_the_size_limit_changes_no_row(client, sessions):
    before = _tables(sessions)
    r = _post(client, b"{" + b" " * MAX_BODY_BYTES + b"}")
    assert r.status_code in (400, 413)  # the body limit of the app can stop it before the page
    assert _tables(sessions) == before
