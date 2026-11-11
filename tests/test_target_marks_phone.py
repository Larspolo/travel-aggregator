"""The mark "at target" and the card of the fares at the target do not scroll sideways on a phone (#847)."""

import os
import threading
import time

import pytest
import uvicorn

from tests.test_mobile_width import socket
from tests.test_target_marks import _target
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow
SHOTS = os.environ.get("SHOTS_DIR")


def test_the_mark_and_the_card_fit_a_phone(trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer(f"{70 + i}.90", f"ICE {100 + i}", fare=f"A long fare name number {i}")
                                   for i in range(6)])
    _target(sessions, trip_id)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for name, ctx in (("phone", p.devices["iPhone 12"]), ("desk", {"viewport": {"width": 1280, "height": 900}})):
                page = browser.new_context(**ctx).new_page()
                for path, sel in (("/", "text=at target"), (f"/trips/{trip_id}", "#at-target")):
                    page.goto(f"http://127.0.0.1:{port}{path}")
                    assert page.locator(sel).first.is_visible()
                    width = page.evaluate("document.documentElement.scrollWidth")
                    assert width <= page.viewport_size["width"], (name, path, width)
                    if SHOTS:
                        page.locator(sel).first.screenshot(path=f"{SHOTS}/{name}-{'list' if path == '/' else 'trip'}.png")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
