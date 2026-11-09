"""The card Recent logins on the settings page, and the names of the browsers in it (#1354)."""

import re

import pytest
from fastapi.testclient import TestClient

from app import login_log
from app.auth import login_limiter, make_password_hash
from app.main import app
from tests.test_totp_login import _csrf

PASSWORD = "correct horse"
FIREFOX_ANDROID = "Mozilla/5.0 (Android 14; Mobile; rv:121.0) Gecko/121.0 Firefox/121.0"
SAFARI_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                 "Version/17.0 Mobile/15E148 Safari/604.1")
EDGE_WINDOWS = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0")
CHROME_MAC = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")


@pytest.fixture
def client(monkeypatch, sessions, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    login_limiter.reset()
    yield TestClient(app, headers={"User-Agent": FIREFOX_ANDROID})
    login_limiter.reset()


def _login(client, password):
    return client.post("/login", data={"password": password, "csrf_token": _csrf(client)}, follow_redirects=False)


def _card(html):
    return html.split("Recent logins", 1)[1].split("</section>", 1)[0]


def _rows(html):
    return re.findall(r"<li>(.*?)</li>", _card(html), re.S)


def _chips(html):
    return [re.search(r'<span class="chip[^"]*">([^<]*)</span>', row).group(1) for row in _rows(html)]


def test_a_failed_and_a_good_login_show_two_rows_newest_first(client):
    assert _login(client, "wrong").status_code == 401
    assert _login(client, PASSWORD).status_code == 303
    html = client.get("/settings").text
    rows = _rows(html)
    assert len(rows) == 2
    assert _chips(html) == ["login", "failed"]
    assert all("testclient" in row and "Firefox on Android" in row for row in rows)


def test_the_card_says_so_when_there_are_no_logins(client, monkeypatch):
    monkeypatch.setattr(login_log, "recent", lambda session, n=20: [])
    _login(client, PASSWORD)
    html = client.get("/settings").text
    assert "No logins yet." in _card(html)
    assert _rows(html) == []


@pytest.mark.parametrize("text, name", [
    (FIREFOX_ANDROID, "Firefox on Android"),
    (SAFARI_IPHONE, "Safari on iPhone"),
    (EDGE_WINDOWS, "Edge on Windows"),
    (CHROME_MAC, "Chrome on macOS"),
])
def test_browser_name_of_real_user_agents(text, name):
    assert login_log.browser_name(text) == name


def test_an_empty_user_agent_is_an_unknown_browser():
    assert login_log.browser_name("") == "unknown browser"


def test_an_unknown_user_agent_shows_its_first_40_characters():
    assert login_log.browser_name("x" * 60) == "x" * 40


def test_a_header_with_markup_shows_as_text(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    login_limiter.reset()
    evil = TestClient(app, headers={"User-Agent": "<script>alert(1)</script>"})
    assert _login(evil, "wrong").status_code == 401
    client = TestClient(app, headers={"User-Agent": FIREFOX_ANDROID})
    _login(client, PASSWORD)
    html = client.get("/settings").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    login_limiter.reset()
