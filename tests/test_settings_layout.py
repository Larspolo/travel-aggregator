"""All settings pages have one frame: the settings navigation in groups, and each card saves its own fields (#925)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.web.pages import SETTINGS_NAV, SETTINGS_PATHS

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _nav(html):
    return html.split('<nav class="settings-nav" aria-label="Settings">')[1].split("</nav>")[0]


def test_the_groups_hold_all_settings_pages():
    assert [g for g, _ in SETTINGS_NAV] == ["App", "Ranking", "Capture"]
    assert SETTINGS_PATHS == ["/settings", "/settings/messages", "/profiles", "/places", "/rates", "/tokens",
                              "/sources/new"]


@pytest.mark.parametrize("path", SETTINGS_PATHS)
def test_each_settings_page_has_the_navigation_and_marks_itself(client, path):
    html = client.get(path).text
    nav = _nav(html)
    assert re.findall(r'<a href="([^"]+)"', nav) == SETTINGS_PATHS
    assert re.findall(r'<a href="([^"]+)" aria-current="page" class="current">', nav) == [path]
    for group, _ in SETTINGS_NAV:
        assert f'<p class="settings-group-name">{group}</p>' in nav
    assert '<a class="back"' not in html  # the navigation replaces the back links
    assert html.count("btn-primary") <= 1


def test_the_app_bar_has_no_settings_sub_pages(client):
    bar = client.get("/").text.split('<div class="nav-links">')[1].split("</div>")[0]
    assert re.findall(r'<a [^>]*href="([^"]+)"', bar) == ["/", "/upcoming", "/captures", "/settings", "/logout"]


def test_each_card_saves_only_its_own_fields(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    r = client.post("/settings/messages", data={"notify_channel": "email", "notify_email": "me@example.org",
                                                "csrf_token": _token(client, "/settings")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings/messages"
    r = client.post("/settings", data={"retention": "12", "csrf_token": _token(client, "/settings")},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings"
    messages = client.get("/settings/messages").text
    assert '<option value="email" selected>' in messages and 'value="me@example.org"' in messages
    general = client.get("/settings").text
    assert re.search(r'name="retention"[^>]*value="12"', general)
    assert 'name="notify_channel"' not in general and 'name="retention"' not in messages


def test_each_form_is_inside_one_card(client):
    for path in ("/settings", "/settings/messages"):
        html = client.get(path).text
        for form in re.findall(r"<form[^>]*>", html):
            assert 'action="/logout"' not in form
        cards = re.findall(r'<section class="card">(.*?)</section>', html, re.S)
        assert sum(c.count("<form") for c in cards) == html.count("<form"), path
        assert all(c.count("<form") <= 1 for c in cards), path
