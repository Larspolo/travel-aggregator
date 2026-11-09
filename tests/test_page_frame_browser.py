"""The app bar on a phone is one line, its menu opens with a tap and has 44 px rows; screenshots (#625)."""

import os
import re
import socket
import threading
import time

import pytest

from app.auth import make_password_hash
from app.models import Trip

PASSWORD = "pw"


@pytest.mark.slow
def test_app_bar_menu_on_a_phone_and_screenshots(sessions, monkeypatch, tmp_path):
    import uvicorn
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        trip = Trip(title="Amsterdam to Berlin", origin_text="Amsterdam", destination_text="Berlin")
        s.add(trip)
        s.commit()
        tid = trip.id
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for scheme in ("light", "dark"):
                for width in (1280, 390):
                    ctx = browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme,
                                              device_scale_factor=2, has_touch=width == 390)
                    page = ctx.new_page()
                    page.goto(base + "/login")
                    page.fill('input[name="password"]', PASSWORD)
                    page.click('button[type="submit"]')
                    page.wait_for_url(re.compile(r".*/$"))
                    for name, path in (("trips", "/"), ("trip", f"/trips/{tid}"), ("settings", "/settings")):
                        page.goto(base + path)
                        page.screenshot(path=os.path.join(shots, f"frame-{name}-{width}-{scheme}.png"))
                    if width == 390:
                        assert page.evaluate("document.documentElement.scrollWidth") <= 390
                        bar = page.locator("nav.topbar").bounding_box()
                        assert bar["height"] < 64
                        assert not page.locator(".nav-links").is_visible()
                        page.locator("details.menu summary").tap()
                        page.wait_for_function("document.querySelector('details.menu').open")
                        links = page.locator(".menu-links a")
                        assert links.count() == 6  # Trips, Upcoming, Pinned, Captures, Settings, Log out (#925, #1301)
                        for i in range(5):
                            assert links.nth(i).bounding_box()["height"] >= 44
                        page.screenshot(path=os.path.join(shots, f"frame-menu-390-{scheme}.png"))
                    else:
                        assert not page.locator("details.menu").is_visible()
                    ctx.close()
            browser.close()
    finally:
        server.should_exit = True
