"""The look of the login page (#633): one centred card, a labelled field, a full-width button, a danger alert."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app

PASSWORD = "correct horse"
CSS = "app/web/static/app.css"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    return TestClient(app)


def _token(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login").text).group(1)


def test_login_is_one_card_with_brand(client):
    html = client.get("/login").text
    assert 'class="login-brand"' in html and 'class="brand"' in html
    assert html.count('class="card login-card"') == 1
    assert html.index('class="login-brand"') < html.index('class="card login-card"') < html.index('name="password"')
    assert "topbar" not in html


def test_password_field_has_label_above_input(client):
    html = client.get("/login").text
    assert re.search(r'<div class="field">\s*<label for="password">Password</label>\s*<input id="password" type="password"', html)


def test_button_is_full_width_primary(client):
    html = client.get("/login").text
    assert '<button type="submit" class="btn btn-primary login-submit">Log in</button>' in html
    assert ".login-submit { width: 100%" in open(CSS, encoding="utf-8").read()


def test_card_is_at_most_24_rem_wide_in_css():
    css = open(CSS, encoding="utf-8").read()
    assert "max-width: 24rem" in css[css.index(".login-card {") :].split("}", 1)[0]


def test_wrong_password_is_a_danger_alert(client):
    r = client.post("/login", data={"password": "wrong", "csrf_token": _token(client)}, follow_redirects=False)
    assert r.status_code == 401
    assert re.search(r'<p class="login-error" role="alert">Wrong password', r.text)
    assert ".login-error { color: var(--danger)" in open(CSS, encoding="utf-8").read()


@pytest.mark.slow
def test_screenshots_and_no_scroll_at_390_px(client, tmp_path):
    import os
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for width in (1280, 390):
                page = browser.new_page(viewport={"width": width, "height": 844})
                page.goto(f"http://127.0.0.1:{port}/login")
                assert page.locator(".login-card").is_visible()
                page.screenshot(path=os.path.join(shots, f"login-{width}.png"), full_page=True)
                if width == 390:
                    assert page.evaluate("document.documentElement.scrollWidth") <= 390
                page.close()
            browser.close()
    finally:
        server.should_exit = True
