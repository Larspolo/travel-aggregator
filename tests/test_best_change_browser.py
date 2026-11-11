"""The list of best offer changes fits at a phone width (#2166)."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_best_change_page import _trip


@pytest.mark.slow
def test_the_list_fits_at_390_px(sessions):
    from playwright.sync_api import sync_playwright

    from app.auth import require_login
    from app.main import app

    trip_id, _, _ = _trip(sessions)
    app.dependency_overrides[require_login] = lambda: None
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    exe = "/opt/pw-browsers/chromium"
    shots = os.environ.get("BEST_CHANGE_SHOTS")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for name, width in (("phone", 390), ("desktop", 1280)):
                page = browser.new_context(viewport={"width": width, "height": 900}).new_page()
                page.goto(f"http://127.0.0.1:{port}/trips/{trip_id}")
                assert page.locator("#trend .best-changes li").count() == 1
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
                if shots:
                    page.locator("#trend").screenshot(path=f"{shots}/best-change-{name}.png")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
        app.dependency_overrides.pop(require_login, None)
