"""The settings page tells an iPhone user to add the app to the Home Screen for Web Push (#798)."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from app import notify
from app.auth import make_password_hash

pytestmark = pytest.mark.slow
PASSWORD = "pw"
HOME_SCREEN_HINT = "On an iPhone or iPad, Web Push works only in the app on the Home Screen"
NO_WEB_PUSH = "This browser has no Web Push."


@pytest.fixture
def live(sessions, monkeypatch):
    public, private = notify.vapid_keys()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:owner@example.com")
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


def _settings_status(live, init_script):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        context = browser.new_context(**p.devices["iPhone 13"])
        context.add_init_script(init_script)
        page = context.new_page()
        page.goto(live + "/login")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.goto(live + "/settings")
        page.wait_for_function("document.getElementById('push-status').textContent.length > 0")
        text = page.locator("#push-status").text_content()
        disabled = page.locator("#push-on").is_disabled() and page.locator("#push-off").is_disabled()
        browser.close()
    return text, disabled


def test_iphone_tab_without_web_push_gets_the_home_screen_hint(live):
    init = "delete window.PushManager; Object.defineProperty(navigator, 'standalone', {get: () => false});"
    text, disabled = _settings_status(live, init)
    assert HOME_SCREEN_HINT in text
    assert NO_WEB_PUSH not in text
    assert disabled


def test_other_browser_without_web_push_keeps_the_old_text(live):
    init = "delete window.PushManager;"
    text, disabled = _settings_status(live, init)
    assert text == NO_WEB_PUSH
    assert disabled
