"""The settings page registers the service worker of Web Push at 390 px with no console error (#514)."""

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


def test_settings_and_the_service_worker_load_at_390_px(live):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        # the browser asks for /favicon.ico by itself: the app has none (not an error of the page)
        page.on("console", lambda m: errors.append(m.text) if m.type == "error"
                and not m.location.get("url", "").endswith("/favicon.ico") else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(live + "/login")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.goto(live + "/settings/messages")
        assert page.locator("#push-on").is_enabled() and page.locator("#push-on").is_visible()
        page.wait_for_function("navigator.serviceWorker.ready.then(r => !!r.active)")
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        sw = page.goto(live + "/sw.js")
        assert sw.status == 200 and "notificationclick" in sw.text()
        assert errors == []
        browser.close()
