"""The "Start from" presets of a new profile (#2520): the form shows the values of a preset, and a save stores them."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import ScoreProfile
from app.profiles import PRESETS, from_config, preset_weights, to_config
from app.ranking import Weights

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _field(page, name):
    return re.search(rf'name="{name}"[^>]*value="([^"]*)"', page).group(1)


def _configs(sessions):
    with sessions() as s:
        return {p.name: p.config_json for p in s.scalars(select(ScoreProfile))}


@pytest.mark.parametrize(("key", "hour", "transfer"), [("budget", "5", "5"), ("time", "40", "25"),
                                                       ("balanced", "15", "10"), ("x", "15", "10")])
def test_a_preset_fills_the_markups(client, key, hour, transfer):
    page = client.get(f"/profiles/new?preset={key}").text
    assert _field(page, "hour_markup") == hour
    assert _field(page, "transfer_markup") == transfer


def test_the_advanced_values_of_each_preset_are_the_defaults():
    markups = {"hour_markup", "transfer_markup"}
    for key in PRESETS:
        got, default = to_config(preset_weights(key)), to_config(Weights())
        assert {k: v for k, v in got.items() if k not in markups} == {k: v for k, v in default.items() if k not in markups}, key
    assert preset_weights("x") == Weights()


def test_the_start_from_line_shows_the_three_links_and_marks_the_selected_one(client):
    page = client.get("/profiles/new?preset=time").text
    for key, label in (("budget", "Budget"), ("balanced", "Balanced"), ("time", "Time is money")):
        assert f'href="/profiles/new?preset={key}"' in page and label in page
    assert re.search(r'href="/profiles/new\?preset=time"[^>]*aria-current="true"', page)
    assert page.count('aria-current="true"') == 1


def test_a_budget_save_stores_the_preset_markups(client, sessions):
    values = to_config(preset_weights("budget"))
    form = {k: v for k, v in values.items() if v is not None}
    r = client.post("/profiles/new", data=form | {"name": "Cheap", "csrf_token": _token(client, "/profiles/new")},
                    follow_redirects=False)
    assert r.status_code == 303
    stored = from_config(_configs(sessions)["Cheap"])
    assert stored.hour_markup == Decimal("5") and stored.transfer_markup == Decimal("5")


def test_a_stored_profile_has_no_start_from_line(client, sessions):
    with sessions() as s:
        p = ScoreProfile(name="Stored", config_json=to_config(Weights()))
        s.add(p)
        s.commit()
        profile_id = p.id
    page = client.get(f"/profiles/{profile_id}").text
    assert "Start from" not in page and "preset=" not in page
