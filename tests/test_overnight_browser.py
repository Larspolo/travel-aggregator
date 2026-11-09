"""The overnight stop cost on the trip page in the browser (#1258): with a hotel cost of €80 the direct night train
ranks above the cheaper itinerary with a night transfer in Köln, with no reload, at 1280 and 390 px."""

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
from tests.test_a11y_browser import check, launch, serious
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow

ROWS = "#rows > tr:not(.detail)"


def _leg(no, frm, to, dep, arr):
    return {"mode": "train", "carrier": "DB", "service_no": no, "from_name": frm, "to_name": to,
            "depart_at": dep, "arrive_at": arr}


DIRECT = {"price_amount": "120.00", "price_currency": "EUR", "fare_name": "Sparpreis", "legs": [
    _leg("NJ 402", "Amsterdam Centraal", "Zürich HB", "2026-12-20T21:00:00+01:00", "2026-12-21T09:00:00+01:00")]}
VIA = {"price_amount": "70.00", "price_currency": "EUR", "fare_name": "Sparpreis", "legs": [
    _leg("ICE 128", "Amsterdam Centraal", "Köln", "2026-12-20T21:00:00+01:00", "2026-12-20T23:40:00+01:00"),
    _leg("ICE 71", "Köln", "Zürich HB", "2026-12-21T06:10:00+01:00", "2026-12-21T09:00:00+01:00")]}


@pytest.fixture
def live(sessions):
    from fastapi.testclient import TestClient

    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, [DIRECT, VIA])
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
    app.dependency_overrides.pop(require_login, None)


def _first(page):
    return page.evaluate(f"document.querySelector('{ROWS}').innerText")


@pytest.mark.parametrize("width", [1280, 390])
def test_the_hotel_cost_puts_the_night_train_first(live, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(live)
        page.wait_for_selector(ROWS)
        assert "ICE 128" in _first(page) and "overnight stop" not in page.inner_text("#rows")
        page.evaluate("window.marker = 1; document.querySelectorAll('details.panel-toggle, details.advanced')"
                      ".forEach(d => d.open = true)")
        page.locator("form.weights input[name=overnight_cost]").fill("80")
        wait_js(page, f"document.querySelector('{ROWS}').innerText.includes('NJ 402')")
        assert page.evaluate("window.marker") == 1  # no reload
        via = page.locator(ROWS, has_text="ICE 128")
        assert "overnight stop in Köln" in via.inner_text() and "80" in via.inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        check("/trips/{id}", width, serious(page))
        browser.close()
