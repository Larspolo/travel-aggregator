"""The filter line of the trip page in the browser (#1455): "Max transfers" 0 shows the line and the best hidden
offer with no reload, its link shows all rows again, and the line has no sideways scroll at 1280 px and on a phone."""

import socket
import threading
import time

import pytest
import uvicorn

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip

from tests.browser_wait import wait_js
from tests.test_a11y_browser import launch
from tests.test_trip_page import ingest

ROWS = "#rows > tr:not(.detail)"

pytestmark = pytest.mark.slow


def _offer(price, stops, service):
    names = ["Amsterdam Centraal", "Utrecht Centraal", "Arnhem Centraal", "Köln Hbf"][: stops + 2]
    legs = [{"mode": "train", "carrier": "NS", "service_no": f"{service}{i}", "from_name": a, "to_name": b,
             "depart_at": f"2026-12-20T{8 + 2 * i:02d}:00:00+01:00",
             "arrive_at": f"2026-12-20T{9 + 2 * i:02d}:00:00+01:00"}
            for i, (a, b) in enumerate(zip(names, names[1:]))]
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Standard", "legs": legs}


OFFERS = [_offer("90.00", 0, "IC 1"), _offer("40.00", 1, "IC 2"), _offer("30.00", 2, "IC 3")]


@pytest.fixture
def live(sessions):
    from fastapi.testclient import TestClient

    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Köln", origin_text="Amsterdam", destination_text="Köln")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, OFFERS)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/trips/{trip_id}?hour_markup=0"
    server.should_exit = True
    thread.join(5)
    app.dependency_overrides.pop(require_login, None)


def _no_scroll(page):
    return page.evaluate("(() => { const p = document.getElementById('trip-filtered');"
                         " return p.scrollWidth <= p.clientWidth"
                         " && document.documentElement.scrollWidth <= window.innerWidth; })()")


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_the_filter_line_works_in_the_browser(live, device):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(**({"viewport": {"width": 1280, "height": 900}} if device == "desktop" else
                                   {**p.devices["Pixel 7"]}))
        page.goto(live)
        page.wait_for_selector(ROWS)
        assert page.locator(ROWS).count() == 3
        assert page.locator("#trip-filtered").is_hidden()
        page.evaluate("window.marker = 1; document.querySelectorAll('details.panel-toggle, details.filters')"
                      ".forEach(d => d.open = true)")
        page.locator("form.weights input[name=max_transfers]").fill("0")
        wait_js(page, "document.getElementById('trip-filtered').innerText.includes('Filters hide 2 of 3 offers')")
        assert page.evaluate("window.marker") == 1  # no reload
        assert page.locator(ROWS).count() == 1
        best = page.locator("#trip-best-hidden")
        assert best.is_visible() and "Best hidden offer" in best.inner_text()
        assert _no_scroll(page)
        page.locator("#trip-filtered a", has_text="max transfers 0").click()
        page.wait_for_load_state()
        wait_js(page, f"document.querySelectorAll('{ROWS}').length === 3")
        assert page.locator("#trip-filtered").is_hidden()
        assert _no_scroll(page)
        browser.close()
