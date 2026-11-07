"""The departure days of a trip work end to end in the browser (#712): the strip shows each day with its best effective
cost, a click on a day filters the table to its offers, a slider keeps that filter, "All days" shows all rows again,
and a tap on a phone filters too (#709, #710, #711)."""

import copy
import os
import re
import socket
import threading
import time
from datetime import date

import pytest
import uvicorn

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_trip_page import ingest, offer

pytestmark = pytest.mark.slow

ROWS = "#rows > tr:not(.detail)"


def offer_on(price, day, service_no):
    """An offer whose legs depart on `day` (YYYY-MM-DD) instead of the day of the ingest body."""
    o = copy.deepcopy(offer(price, service_no))
    for leg in o["legs"]:
        leg["depart_at"] = leg["depart_at"].replace("2026-12-20", day)
        leg["arrive_at"] = leg["arrive_at"].replace("2026-12-20", day)
    return o


@pytest.fixture
def days_trip(sessions):
    """A client with the owner login and a trip from 18 to 22 December with offers on 4 of the 5 days."""
    with sessions() as s:
        tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 18), date_to=date(2026, 12, 22))
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield trip_id
    app.dependency_overrides.pop(require_login, None)


@pytest.fixture
def live(days_trip, sessions):
    """The app on a real port, so that a browser can load the trip page and its htmx requests."""
    from fastapi.testclient import TestClient

    trip_id = days_trip
    client = TestClient(app)
    with sessions() as s:
        token = tokens.create(s, "test-days")
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [
        offer_on("100.00", "2026-12-18", "ICE 201"),
        offer_on("60.00", "2026-12-19", "ICE 301"),
        offer_on("120.00", "2026-12-19", "ICE 302"),
        offer_on("90.00", "2026-12-21", "ICE 401"),
        offer_on("80.00", "2026-12-22", "ICE 501"),
    ])
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


def number(text):
    return float(re.search(r"\d+(?:\.\d+)?", text.replace(",", "")).group(0))


def test_the_departure_days_filter_the_table_end_to_end(live):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(live)
        page.wait_for_selector(ROWS)

        # the strip: 5 days, 20 December without offers, 19 December with its lower effective cost
        chips = page.locator("#trip-days a.chip.day, #trip-days span.chip.day")
        assert chips.count() == 6  # "All days" and the 5 days
        assert "no offers" in page.locator("#trip-days .chip.day", has_text="20-12").inner_text()
        day19 = page.locator("#trip-days a.chip.day", has_text="19-12")
        best19 = number(day19.locator(".day-best").inner_text())
        assert page.locator(ROWS).count() == 5
        totals = [number(page.locator(ROWS, has_text=s).locator(".total").inner_text())
                  for s in ("ICE 301", "ICE 302")]
        assert best19 == min(totals)

        # a click on 19 December: only its 2 rows
        day19.click()
        page.wait_for_function(f"document.querySelectorAll(\"{ROWS}\").length === 2")
        assert page.locator(ROWS, has_text="ICE 301").count() == 1
        assert page.locator(ROWS, has_text="ICE 302").count() == 1

        # a slider change keeps the day filter
        slider = page.locator("form.weights input[type=range][name=hour_markup]")
        with page.expect_response(lambda r: "hour_markup=50" in r.url and "day=2026-12-19" in r.url):
            slider.evaluate("el => { el.value = '50'; el.dispatchEvent(new Event('input', {bubbles: true})); }")
        page.wait_for_function(f"document.querySelectorAll(\"{ROWS}\").length === 2")
        assert page.locator(ROWS).count() == 2

        # "All days" shows all rows again
        page.locator("#trip-days a.chip.day", has_text="All days").click()
        page.wait_for_function(f"document.querySelectorAll(\"{ROWS}\").length === 5")
        browser.close()


def test_on_a_phone_the_page_does_not_scroll_sideways_and_a_tap_filters_the_days(live):
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        context = browser.new_context(**p.devices["iPhone 13"])
        page = context.new_page()
        page.goto(live)
        page.wait_for_selector(ROWS)
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")

        page.locator("#trip-days a.chip.day", has_text="19-12").tap()
        page.wait_for_function(f"document.querySelectorAll(\"{ROWS}\").length === 2")
        assert page.locator(ROWS).count() == 2
        browser.close()
