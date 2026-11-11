"""The owner sorts the trips list by price with the keyboard only, at 390 px (#1973)."""

import socket
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import uvicorn
from sqlalchemy.orm import Session

from app.auth import require_login
from app.main import app
from app.models import Fare, Itinerary, Trip
from tests.test_a11y_browser import launch

pytestmark = pytest.mark.slow
T = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


@pytest.fixture
def server(sessions):
    """The live server with 3 trips; the cheapest trip is not the first by date; the login is not checked here."""
    with Session(sessions.kw["bind"]) as s:
        for title, price in [("Amsterdam → Zürich", "120.00"), ("Utrecht → Rome", None), ("Utrecht → Oslo", "35.00")]:
            trip = Trip(title=title, origin_text="Utrecht", destination_text=title.split()[-1])
            s.add(trip)
            if price:
                it = Itinerary(trip=trip, fingerprint=title, depart_at=T, arrive_at=T, duration_min=60)
                it.fares.append(Fare(source="x", latest_price=Decimal(price), currency="EUR", latest_captured_at=T))
                s.add(it)
        s.commit()
    app.dependency_overrides[require_login] = lambda: None
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)
    app.dependency_overrides.pop(require_login, None)


def test_the_owner_sorts_by_price_with_the_keyboard(server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 900})
        page.goto(f"{server}/")
        assert page.locator(".trip-grid .card").count() == 3
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        for _ in range(60):
            if page.evaluate("document.activeElement && document.activeElement.textContent.trim()") == "Price":
                break
            page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.textContent.trim()") == "Price"
        page.keyboard.press("Enter")
        page.wait_for_url("**sort=price**")
        assert page.locator(".trip-grid .card h2").first.inner_text() == "Utrecht → Oslo"
        assert page.locator(".trip-grid .card h2").last.inner_text() == "Utrecht → Rome"
        assert page.locator('.trip-sort a[aria-current="true"]').inner_text() == "Price"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        browser.close()
