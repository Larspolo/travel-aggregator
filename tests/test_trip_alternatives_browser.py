"""The alternative destinations of a trip in the browser (#1426): the trip Amsterdam → Zürich with the other
destination Basel shows the ICE to Basel next to the train to Zürich, with the egress of Basel SBB in its breakdown, at
1280 and 390 px."""

import socket
import threading
import time

import pytest
import uvicorn
from sqlalchemy import select

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_a11y_browser import check, launch, serious
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow

ROWS = "#rows > tr:not(.detail)"


def _offer(no, to, price):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Sparpreis", "legs": [
        {"mode": "train", "carrier": "DB", "service_no": no, "from_name": "Amsterdam Centraal", "to_name": to,
         "depart_at": "2026-12-20T08:00:00+01:00", "arrive_at": "2026-12-20T15:00:00+01:00"}]}


ZURICH = _offer("ICE 105", "Zürich HB", "90.00")
BASEL = _offer("ICE 127", "Basel SBB", "80.00")


@pytest.fixture
def server(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
    app.dependency_overrides[require_login] = lambda: None
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", token
    srv.should_exit = True
    thread.join(5)
    app.dependency_overrides.pop(require_login, None)


@pytest.mark.parametrize("width", [1280, 390])
def test_the_basel_ice_shows_next_to_the_zurich_train(server, sessions, width):
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright

    base, token = server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(f"{base}/trips/new")
        page.fill("input[name=title]", "Amsterdam – Zürich")
        page.fill("input[name=origin_text]", "Amsterdam")
        page.fill("input[name=destination_text]", "Zürich")
        page.fill("input[name=destination_alt_text]", "Basel")
        page.fill("input[name=date_from]", "2026-12-20")
        page.click("form[action=\"/trips/new\"] button[type=submit]")
        page.wait_for_url(f"{base}/")
        with sessions() as s:
            trip_id = s.scalar(select(Trip.id).where(Trip.destination_alt_text == "Basel"))
        page.goto(f"{base}/places")
        page.fill("#place_text", "Basel SBB")  # a place matches the station name exactly (app/door.py)
        page.select_option("#kind", "egress")
        page.fill("#minutes", "40")
        page.fill("#cost", "5")
        with page.expect_navigation():
            page.locator("form:has(#place_text) button[type=submit]").click()
        assert "Basel SBB" in page.inner_text("main")
        ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, [ZURICH, BASEL])

        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        rows = page.inner_text("#rows")
        assert "ICE 105" in rows and "ICE 127" in rows
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        check("/trips/{id}", width, serious(page))
        page.evaluate("document.querySelectorAll('#rows details').forEach(d => d.open = true)")
        basel = page.locator(ROWS, has_text="ICE 127")
        text = basel.inner_text() + basel.locator("xpath=following-sibling::tr[1]").inner_text()
        assert "egress time" in text and "€5 egress cost" in text, text
        assert "egress" not in page.locator(ROWS, has_text="ICE 105").inner_text()

        page.goto(f"{base}/trips/{trip_id}/captures")
        assert "These offers do not match the trip" not in page.inner_text("body")
        page.goto(f"{base}/captures")
        assert "These offers do not match the trip" not in page.inner_text("body")
        browser.close()
