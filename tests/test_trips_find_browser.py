"""The owner finds a trip among 40 trips with the keyboard, at 1280 px and at 390 px (#1223)."""

import socket
import threading
import time
from datetime import date, timedelta

import pytest
import uvicorn
from sqlalchemy.orm import Session

from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_a11y_browser import launch, serious

pytestmark = pytest.mark.slow

PLACES = ["Paris", "Rome", "Lisbon", "Berlin", "Vienna", "Madrid", "Oslo", "Prague", "Athens", "Dublin"]


@pytest.fixture
def server(sessions):
    """The live server with 40 active trips and one archived trip; the login is not checked here."""
    with Session(sessions.kw["bind"]) as s:
        s.add(Trip(title="Amsterdam → Zürich", origin_text="Amsterdam", destination_text="Zürich",
                   date_from=date(2026, 12, 20), status="planning"))
        s.add(Trip(title="Zürich Christmas", origin_text="Amsterdam", destination_text="Zürich",
                   date_from=date(2026, 12, 24), status="archived"))
        for i in range(39):
            dest = PLACES[i % len(PLACES)]
            s.add(Trip(title=f"Trip {i + 1:02d} {dest}", origin_text="Amsterdam", destination_text=dest,
                       date_from=date(2027, 1, 1) + timedelta(days=i), status="planning"))
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


@pytest.mark.parametrize("width", [1280, 390])
def test_the_owner_finds_the_trip_with_the_keyboard(server, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(f"{server}/")
        assert page.locator(".trip-grid .card").count() == 40
        assert page.get_by_text("In the archive").count() == 0

        for _ in range(40):  # Tab from the top of the page until the search field has the focus
            if page.evaluate("document.activeElement && document.activeElement.id") == "trip-q":
                break
            page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == "trip-q"
        page.keyboard.type("zur")
        page.keyboard.press("Enter")
        page.wait_for_url("**q=zur**")

        assert page.locator(".trip-grid .card").count() == 2
        assert page.get_by_text("In the archive (1)").count() == 1
        assert page.get_by_text("Zürich Christmas").count() >= 1
        assert page.get_by_text("Trip 01 Paris").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert serious(page) == set()
        browser.close()
