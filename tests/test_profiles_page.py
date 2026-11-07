"""The score profiles page (#233): list, set the default, rename and delete a profile."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def two_profiles(sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json=to_config(Weights(hour_markup=5))))
        s.add(ScoreProfile(name="Comfort", is_default=False, config_json=to_config(Weights(transfer_markup=30))))
        s.commit()
        return {p.name: p.id for p in s.scalars(select(ScoreProfile))}


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _post(c, path, **data):
    return c.post(path, data=data | {"csrf_token": _token(c, "/profiles")}, follow_redirects=False)


def _defaults(sessions):
    with sessions() as s:
        return {p.name: p.is_default for p in s.scalars(select(ScoreProfile))}


def test_no_login_redirects():
    r = TestClient(app).get("/profiles", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_page_lists_profiles_with_their_values(client, two_profiles):
    page = client.get("/profiles").text
    assert "Cheap" in page and "Comfort" in page
    assert "€5/h" in page and "€30" in page
    assert page.count('badge">default') == 1


def test_set_default_moves_the_mark(sessions, client, two_profiles):
    r = _post(client, f"/profiles/{two_profiles['Comfort']}/default")
    assert r.status_code == 303 and r.headers["location"] == "/profiles"
    assert _defaults(sessions) == {"Cheap": False, "Comfort": True}
    r = _post(client, f"/profiles/{two_profiles['Cheap']}/default")
    assert r.status_code == 303
    assert _defaults(sessions) == {"Cheap": True, "Comfort": False}


def test_set_default_on_missing_profile_gives_404(client, two_profiles):
    assert _post(client, "/profiles/9999/default").status_code == 404


def test_rename_to_a_free_name_changes_it(sessions, client, two_profiles):
    r = _post(client, f"/profiles/{two_profiles['Comfort']}/rename", name="  Relaxed  ")
    assert r.status_code == 303
    with sessions() as s:
        assert sorted(p.name for p in s.scalars(select(ScoreProfile))) == ["Cheap", "Relaxed"]


def test_rename_to_an_existing_name_shows_an_error_and_changes_nothing(sessions, client, two_profiles):
    before = _defaults(sessions)
    r = _post(client, f"/profiles/{two_profiles['Comfort']}/rename", name="Cheap")
    assert r.status_code == 422
    assert "exists already" in r.text and "nothing changed" in r.text
    with sessions() as s:
        assert sorted(p.name for p in s.scalars(select(ScoreProfile))) == ["Cheap", "Comfort"]
    assert _defaults(sessions) == before


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_rename_with_a_bad_name_changes_nothing(sessions, client, two_profiles, name):
    r = _post(client, f"/profiles/{two_profiles['Comfort']}/rename", name=name)
    assert r.status_code == 422
    with sessions() as s:
        assert sorted(p.name for p in s.scalars(select(ScoreProfile))) == ["Cheap", "Comfort"]


def test_delete_removes_the_row(sessions, client, two_profiles):
    r = _post(client, f"/profiles/{two_profiles['Comfort']}/delete")
    assert r.status_code == 303 and r.headers["location"] == "/profiles"
    with sessions() as s:
        assert [p.name for p in s.scalars(select(ScoreProfile))] == ["Cheap"]


def test_delete_on_missing_profile_gives_404(client, two_profiles):
    assert _post(client, "/profiles/9999/delete").status_code == 404


@pytest.mark.parametrize("path", ["/profiles/{id}/default", "/profiles/{id}/rename", "/profiles/{id}/delete"])
def test_actions_need_csrf(sessions, client, two_profiles, path):
    pid = two_profiles["Comfort"]
    r = client.post(path.format(id=pid), data={"name": "Other"}, follow_redirects=False)
    assert r.status_code == 403
    assert _defaults(sessions) == {"Cheap": True, "Comfort": False}
    with sessions() as s:
        assert sorted(p.name for p in s.scalars(select(ScoreProfile))) == ["Cheap", "Comfort"]
