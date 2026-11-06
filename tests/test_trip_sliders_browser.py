"""A slider change on the trip page re-ranks the rows without a page reload (#14)."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

pytestmark = pytest.mark.slow


@pytest.fixture
def live(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
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


def test_a_slider_change_reranks_without_a_reload(live):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page()
        page.goto(live)
        cells = page.locator("#rows td.cost")
        assert cells.first.inner_text().endswith("= €210")  # the direct one first with the default markups
        page.evaluate("window.__same = true")
        page.locator("form.weights input[name=hour_markup]").fill("0")  # fill dispatches input on a range field
        page.wait_for_function("document.querySelector('#rows td.cost').textContent.endsWith('= €99.90')")
        assert page.evaluate("window.__same") is True  # no reload
        assert page.locator("output[name=hour_value]").inner_text() == "0"
        browser.close()
