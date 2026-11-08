"""A link to #it-<id> opens the row of that itinerary and its detail, in Chromium (#814)."""

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


def test_opening_the_page_with_the_hash_opens_only_that_row(live):
    from playwright.sync_api import sync_playwright

    url, _, second = live
    with sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page()
        page.goto(f"{url}#it-{second}")
        page.wait_for_function(f"{OPEN} === 1")
        assert page.evaluate(
            f"document.getElementById('it-{second}').nextElementSibling.querySelector('details').open")
        browser.close()


def test_a_click_on_a_link_to_the_row_opens_only_that_row(live):
    from playwright.sync_api import sync_playwright

    url, first, second = live
    with sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page()
        page.goto(url)
        page.evaluate(f"document.body.insertAdjacentHTML('beforeend', '<a id=\"row-link\" href=\"#it-{second}\">row</a>')")
        assert page.evaluate(OPEN) == 0
        page.click("#row-link")
        page.wait_for_function(f"{OPEN} === 1")
        assert page.evaluate(
            f"document.getElementById('it-{second}').nextElementSibling.querySelector('details').open")
        browser.close()
