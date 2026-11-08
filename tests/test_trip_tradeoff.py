"""The break-even hour value in the expanded row of the trip table (#895, epic #892)."""

import os
import re
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import uvicorn
from sqlalchemy import select

from app.models import Itinerary
from app.ranking import Weights
from app.web.pages import row_cost
from tests.test_compare_tradeoff import timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

LINE = "2 h faster, €25 more than the best: better above €12.50/h (yours: €10/h)"


def _lines(page):
    rows = re.findall(r'<tr id="it-(\d+)">.*?(?:<p class="tradeoff muted">(.*?)</p>|'
                      r'(?=<tr id="it-)|$)', page, re.S)
    return {int(i): re.sub(r"<[^>]+>", "", text) for i, text in rows if text}  # the link tag is no text (#920)


def test_the_other_row_shows_the_break_even_and_the_best_row_shows_none(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    with sessions() as s:
        ids = {i.duration_min: i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "10"}).text
    assert page.count('class="tradeoff') == 1
    assert _lines(page) == {ids[180]: LINE}


def test_both_costs_are_equal_at_the_shown_hour_value(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    with sessions() as s:
        by_dur = {i.duration_min: i for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}
        weights = Weights(hour_markup=Decimal("12.50"))
        stale_before = datetime.now(timezone.utc) - timedelta(hours=weights.stale_hours)
        a, b = (row_cost(by_dur[d], by_dur[d].fares, [], weights, stale_before, {})[1].total for d in (300, 180))
    assert abs(a - b) <= Decimal("0.01")


@pytest.fixture
def two_live(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/trips/{trip_id}?hour_markup=10"
    server.should_exit = True
    thread.join(5)


@pytest.mark.slow
def test_screenshots_of_an_expanded_row_with_the_break_even(two_live):
    from playwright.sync_api import sync_playwright

    out = os.environ.get("SCREENSHOT_DIR")
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        for width in (1280, 390):
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
            page.goto(two_live)
            page.locator("details summary", has_text="Legs and fares").nth(1).click()
            line = page.locator("p.tradeoff")
            line.wait_for()
            assert line.inner_text() == LINE
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            if out:
                page.locator("tr.detail").nth(1).screenshot(path=f"{out}/tradeoff-{width}.png")
            page.close()
        browser.close()
