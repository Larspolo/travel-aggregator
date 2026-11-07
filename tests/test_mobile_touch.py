"""The phone check of #338 with touch, so that no person checks it: on a phone device the pages do not scroll
sideways, a tap on a weight slider ranks the table again, each itinerary is a card that fits the box (#593), and a tap opens a row."""

import copy
import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

PHONE = "iPhone 13"  # 390 px wide, touch, mobile


def direct(price):
    """One leg from Amsterdam to Zürich with the same times as the offer with 1 transfer."""
    o = offer(price, "ICE 77", fare="Flexpreis")
    o["legs"] = [copy.deepcopy(o["legs"][0])]
    o["legs"][0].update(to_name="Zürich HB", arrive_at="2026-12-20T15:26:00+01:00")
    return o


@pytest.fixture
def live(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.00", "ICE 105", carrier="Carrier with a long name",
                                         fare="A long fare name"), direct("120.00")])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", trip_id
    server.should_exit = True
    thread.join(5)


def _launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


def _first_service(page):
    return page.locator("#table tbody tr:not(.detail)").first.locator("td").nth(3).inner_text()


def test_the_trips_list_and_the_trip_page_work_with_touch_on_a_phone(live):
    from playwright.sync_api import sync_playwright

    base, tid = live
    with sync_playwright() as p:
        browser = _launch(p)
        context = browser.new_context(**p.devices[PHONE])
        page = context.new_page()
        width = page.viewport_size["width"]

        page.goto(base + "/")
        assert page.evaluate("document.documentElement.scrollWidth") <= width

        page.goto(f"{base}/trips/{tid}")
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert "ICE 105" in _first_service(page)  # the cheap offer with 1 transfer ranks first

        # On a phone the weights are one closed <details> (#593): a tap opens it.
        page.locator(".panel-toggle > summary").tap()
        page.wait_for_function("document.querySelector('.panel-toggle').open", timeout=5000)
        # A tap at the right end of the transfer slider sets a high markup: the direct offer ranks first.
        slider = page.locator('input[type="range"][name="transfer_markup"]')
        slider.scroll_into_view_if_needed()
        box = slider.bounding_box()
        with page.expect_response(lambda r: f"/trips/{tid}?" in r.url):
            page.touchscreen.tap(box["x"] + box["width"] - 2, box["y"] + box["height"] / 2)
        assert int(slider.input_value()) > 90
        page.wait_for_function("document.querySelector('#table tbody td:nth-child(4)').innerText.includes('ICE 77')")

        # Each itinerary is a card (#593): the table box does not scroll sideways, and the page does not either.
        table = page.locator("#table")
        assert table.evaluate("e => e.scrollWidth <= e.clientWidth")
        assert page.evaluate("window.scrollX") == 0

        # A tap on "Legs and fares" opens the row.
        summary = page.locator("#table tr.detail summary").first
        summary.tap()
        # The browser makes the click of a tap from a gesture after the touch events: it can come after tap() returns,
        # so wait for the open row and do not read it once (#508).
        page.wait_for_function("document.querySelector('#table tr.detail summary').parentElement.open", timeout=5000)
        if os.environ.get("TOUCH_SHOT"):  # an image for the evidence comment of a check ticket
            page.screenshot(path=os.environ["TOUCH_SHOT"], full_page=True)
        browser.close()
