"""A click on Pin updates the trip page in place (#666): no reload, the scroll position stays, the row shows
"pinned"."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow


@pytest.fixture
def live(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer(f"{80 + i}.00", f"ICE {100 + i}") for i in range(12)])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/trips/{trip_id}"
    server.should_exit = True
    thread.join(5)


def test_pin_keeps_the_scroll_position_and_shows_pinned(live):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 600})
        page.goto(live)
        last = page.locator("#rows tr.offer, #rows > tr:not(.detail)").last
        last.scroll_into_view_if_needed()
        before = page.evaluate("window.scrollY")
        assert before > 0
        page.evaluate("window.__same = true")
        last.locator("button[aria-label=Pin]").click()
        page.wait_for_function("document.querySelectorAll('#rows .muted').length && "
                               "[...document.querySelectorAll('#rows td')].some(td => td.textContent.includes('pinned'))")
        assert page.evaluate("window.__same") is True  # no reload
        assert abs(page.evaluate("window.scrollY") - before) < 5
        browser.close()
