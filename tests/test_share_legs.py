"""The legs of each row on the shared page (#906)."""

import os
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.main import app
from tests.test_share import share
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def test_a_row_with_two_legs_shows_both_legs_and_the_transfer(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    page = TestClient(app).get(share(client, trip_id)).text
    legs = page[page.index('<div class="timeline legs">'):page.index("</details>")]
    assert legs.count('class="leg"') == 2
    assert "DB ICE 105" in legs and "SBB IC 61" in legs
    for clock, place in (("07:34", "Amsterdam Centraal"), ("14:02", "Basel SBB"), ("14:33", "Basel SBB"),
                         ("15:26", "Zürich HB")):
        assert f"<time>{clock}</time> {place}" in legs
    assert "Transfer at Basel SBB: 0h 31" in legs
    assert "<form" not in page and "bahn.de" not in page


@pytest.mark.slow
def test_screenshots_of_an_open_row_on_the_shared_page(trip):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    link = share(client, trip_id)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    out = os.environ.get("SCREENSHOT_DIR")
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for width in (1280, 390):
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
                page.goto(f"http://127.0.0.1:{port}{link}")
                page.locator("details summary", has_text="Legs").first.click()
                page.locator(".leg").first.wait_for()
                assert page.evaluate("document.documentElement.scrollWidth") <= width
                if out:
                    page.screenshot(path=f"{out}/shared-legs-{width}.png", full_page=True)
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
