"""The event upload form works with a keyboard and at a phone width, and only on the new-trip form (#2495)."""

import os
import socket
import threading
import time
from datetime import date

import pytest
import uvicorn

from app.auth import require_login
from app.main import app
from app.models import Trip

pytestmark = pytest.mark.slow

FIELDS = [
    ("f-event-file", "Event file (.ics)"),
    ("f-event-origin", "Origin"),
    ("f-event-margin", "Margin before the event (minutes)"),
]


@pytest.fixture
def server(sessions):
    """The app on a real port, with a trip for the edit form; the login is not needed for these pages."""
    with sessions() as s:
        t = Trip(title="Team day", origin_text="Amsterdam", destination_text="Berlin",
                 date_from=date(2026, 12, 21), date_to=date(2026, 12, 21))
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
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
    app.dependency_overrides.pop(require_login, None)


def launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


@pytest.mark.parametrize("width", [390, 1280])
def test_new_trip_form_fields_have_labels_focus_and_no_sideways_scroll(server, width):
    from playwright.sync_api import sync_playwright

    base, _ = server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(f"{base}/trips/new")
        for field_id, label in FIELDS:
            assert page.locator(f'label[for="{field_id}"]').inner_text().strip() == label
            page.locator(f"#{field_id}").focus()
            assert page.evaluate("document.activeElement.id") == field_id
        page.locator("#f-event-file").focus()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == "f-event-origin"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == "f-event-margin"
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        browser.close()


def test_edit_form_has_no_event_section(server):
    from playwright.sync_api import sync_playwright

    base, trip_id = server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 800})
        page.goto(f"{base}/trips/{trip_id}/edit")
        assert page.locator('form[action="/trips/from-event"]').count() == 0
        for field_id, _ in FIELDS:
            assert page.locator(f"#{field_id}").count() == 0
        browser.close()
