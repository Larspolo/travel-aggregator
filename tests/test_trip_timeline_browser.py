"""A click on a bar of the timeline opens the detail of its row, in Chromium (#815)."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

OPEN = "document.querySelectorAll('tr.detail details[open]').length"


@pytest.fixture
def live(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.00", "ICE 1"), offer("120.00", "ICE 2")])
    with sessions() as s:
        first, second = [it.id for it in s.query(Itinerary).filter_by(trip_id=trip_id).order_by(Itinerary.id)]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/trips/{trip_id}", first, second
    server.should_exit = True
    thread.join(5)


def _browser(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if os.path.exists(exe) \
        else p.chromium.launch()


def test_a_click_on_a_timeline_bar_opens_its_row(live):
    from playwright.sync_api import sync_playwright

    url, _, second = live
    with sync_playwright() as p:
        browser = _browser(p)
        for width in (1280, 390):
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(url)
            page.click("#trip-timeline summary")
            bar = page.locator(f'.timeline-bar[href="#it-{second}"]')
            assert bar.bounding_box()["height"] >= 24
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            if os.environ.get("SHOTS"):  # the screenshots of the PR
                page.screenshot(path=os.path.join(os.environ["SHOTS"], f"timeline-{width}.png"), full_page=True)
            bar.click()
            page.wait_for_function(f"{OPEN} === 1")
            assert page.evaluate(
                f"document.getElementById('it-{second}').nextElementSibling.querySelector('details').open")
            page.close()
        browser.close()
