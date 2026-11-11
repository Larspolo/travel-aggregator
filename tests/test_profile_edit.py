"""The profile page (#1013): make a profile and edit all its weights with no trip."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import ScoreProfile, Trip
from app.profiles import from_config, to_config
from app.ranking import Weights
from app.web.pages import resolve_weights

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def comfort(sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", config_json=to_config(Weights(hour_markup=Decimal("5")))))
        p = ScoreProfile(name="Comfort", config_json=to_config(Weights(transfer_markup=Decimal("30"),
                                                                      stale_hours=12)))
        s.add(p)
        s.commit()
        return p.id


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _post(c, path, **data):
    return c.post(path, data=data | {"csrf_token": _token(c, "/profiles/new")}, follow_redirects=False)


def _configs(sessions):
    with sessions() as s:
        return {p.name: p.config_json for p in s.scalars(select(ScoreProfile))}


def test_profiles_page_links_new_and_edit(client, comfort):
    page = client.get("/profiles").text
    assert 'href="/profiles/new"' in page and f'href="/profiles/{comfort}"' in page


def test_new_form_has_the_defaults(client):
    page = client.get("/profiles/new").text
    assert 'name="hour_markup"' in page and f'value="{Weights.hour_markup}"' in page
    assert 'name="stale_hours"' in page and "Advanced" in page


def test_a_new_profile_is_stored_and_listed(client, sessions):
    r = _post(client, "/profiles/new", name=" Fast ", hour_markup="40", stale_hours="6")
    assert r.status_code == 303 and r.headers["location"] == "/profiles"
    assert from_config(_configs(sessions)["Fast"]) == Weights(hour_markup=Decimal("40"), stale_hours=6)
    assert "Fast" in client.get("/profiles").text


def test_edit_form_shows_the_stored_weights(client, comfort):
    page = client.get(f"/profiles/{comfort}").text
    assert 'value="Comfort"' in page
    assert re.search(r'name="transfer_markup"[^>]*value="30"', page)
    assert re.search(r'name="stale_hours"[^>]*value="12"', page)
    assert re.search(r'name="night_hour_markup"[^>]*value=""', page)


def test_a_save_stores_the_changed_weights_and_the_trip_ranks_with_them(client, sessions, comfort):
    form = {k: v for k, v in to_config(Weights(transfer_markup=Decimal("30"), stale_hours=12)).items() if v is not None}
    r = _post(client, f"/profiles/{comfort}", **(form | {"name": "Comfort", "hour_markup": "77"}))
    assert r.status_code == 303
    stored = from_config(_configs(sessions)["Comfort"])
    assert stored == Weights(hour_markup=Decimal("77"), transfer_markup=Decimal("30"), stale_hours=12)
    with sessions() as s:
        trip = Trip(title="Lisbon", profile_id=comfort)
        s.add(trip)
        s.commit()
        weights, chosen = resolve_weights(s, trip, {}, None)
    assert chosen.id == comfort and weights.hour_markup == Decimal("77")


@pytest.mark.parametrize("data", [{"hour_markup": "101"}, {"stale_hours": "0"}, {"night_adjust": "x"},
                                  {"early_limit": "25:00"}, {"name": "Cheap"}, {"name": "  "}])
def test_a_bad_value_or_name_gives_422_and_changes_nothing(client, sessions, comfort, data):
    before = _configs(sessions)
    r = _post(client, f"/profiles/{comfort}", **({"name": "Comfort"} | data))
    assert r.status_code == 422 and "nothing changed" in r.text and 'role="alert"' in r.text
    r = _post(client, "/profiles/new", **({"name": "New"} | data))
    assert r.status_code == 422 and "nothing changed" in r.text
    assert _configs(sessions) == before


def test_a_missing_profile_gives_404(client):
    assert client.get("/profiles/999999").status_code == 404
    assert _post(client, "/profiles/999999", name="X").status_code == 404
