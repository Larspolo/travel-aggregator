"""The CO₂ cost on the trip page in the browser (#1419): a CO₂ price of €0.10 per kg puts a train of 6 h above a
cheaper flight of 2 h, with no reload, at 1280 and 390 px."""

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


FLIGHT = {"price_amount": "60.00", "price_currency": "EUR", "fare_name": "Light", "legs": [
    {"mode": "flight", "carrier": "KL", "service_no": "KL 1975", "from_name": "Amsterdam Schiphol",
     "to_name": "Zürich Airport", "depart_at": "2026-12-20T09:00:00+01:00", "arrive_at": "2026-12-20T11:00:00+01:00"}]}
TRAIN = {"price_amount": "75.00", "price_currency": "EUR", "fare_name": "Sparpreis", "legs": [
    {"mode": "train", "carrier": "DB", "service_no": "ICE 105", "from_name": "Amsterdam Centraal",
     "to_name": "Zürich HB", "depart_at": "2026-12-20T09:00:00+01:00", "arrive_at": "2026-12-20T15:00:00+01:00"}]}


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
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, [FLIGHT, TRAIN])
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


def _first(page):
    return page.evaluate(f"document.querySelector('{ROWS}').innerText")


@pytest.mark.parametrize("width", [1280, 390])
def test_the_co2_price_puts_the_train_first(live, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(live)
        page.wait_for_selector(ROWS)
        assert "KL 1975" in _first(page)
        page.evaluate("window.marker = 1; document.querySelectorAll('details.panel-toggle, details.advanced')"
                      ".forEach(d => d.open = true)")
        page.locator("form.weights input[name=co2_price_kg]").fill("0.10")
        wait_js(page, f"document.querySelector('{ROWS}').innerText.includes('ICE 105')")
        assert page.evaluate("window.marker") == 1  # no reload
        page.evaluate("document.querySelectorAll('#rows details').forEach(d => d.open = true)")
        text = page.locator("#rows").inner_text()
        breakdown = page.locator(ROWS, has_text="KL 1975").locator(".breakdown").text_content()
        assert "€18 CO₂ 180 kg" in breakdown, breakdown
        assert "CO₂ about 180 kg per traveler (estimate)" in text
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        check("/trips/{id}", width, serious(page))
        browser.close()
