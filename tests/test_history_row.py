"""The expanded row of the trip table loads the price history of its itinerary on first open (#242).
The trip page carries only the URL of the history of each row, not the history itself."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def test_the_trip_page_has_the_history_url_of_each_row_and_no_history_table(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    page = client.get(f"/trips/{trip_id}").text
    assert f'hx-get="/trips/{trip_id}/itineraries/' in page
    assert '/history" hx-trigger="toggle from:closest details once"' in page
    assert '<table class="history">' not in page


@pytest.fixture
def live(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
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


@pytest.mark.slow
def test_opening_a_row_shows_its_price_history(live):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page()
        page.goto(live)
        assert page.locator('table.history').count() == 0
        page.locator("details summary", has_text="Legs and fares").first.click()
        page.wait_for_selector("table.history")
        assert page.locator("table.history").first.is_visible()
        browser.close()
