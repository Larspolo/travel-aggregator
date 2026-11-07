"""The profiles and places pages are cards with fields and an empty state (#631)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _card(html, title):
    return re.search(r'<section class="card">\s*<div class="card-header"><h2>' + re.escape(title), html)


def test_empty_places_has_cards_fields_and_empty_state(client):
    html = client.get("/places").text
    assert _card(html, "Add a place") and _card(html, "Places")
    assert re.search(r'<div class="empty">\s*<p>You have no places.</p>\s*<div class="toolbar"><a class="btn', html)
    for label in re.findall(r"<label[^>]*>", html):
        assert "for=" in label
    assert html.count('<div class="field') == 4


def test_empty_profiles_has_empty_state_with_action(client, sessions):
    from app.models import ScoreProfile
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    html = client.get("/profiles").text
    assert _card(html, "Profiles")
    assert re.search(r'<p>You have no profiles.</p>\s*<div class="toolbar"><a class="btn btn-primary" href="/">', html)


def test_place_row_has_delete_icon_button(client):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/places").text).group(1)
    client.post("/places", data={"place_text": "home", "kind": "access", "minutes": "5", "cost": "1",
                                 "csrf_token": token})
    html = client.get("/places").text
    assert '<li class="item">' in html and 'aria-label="Delete home"' in html
