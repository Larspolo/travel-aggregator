"""The "Copy summary" button in Chromium (#2162): the clipboard, the textarea with no Clipboard API, and the
out-of-band update after a weight change. 1280 and 390 px."""

import copy
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
from tests.test_mode_hours_browser import FLIGHT, TRAIN
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow

CHEAP_TRAIN = {**copy.deepcopy(TRAIN), "price_amount": "40.00"}
SECOND_TRAIN = copy.deepcopy(CHEAP_TRAIN)
SECOND_TRAIN["price_amount"] = "45.00"
SECOND_TRAIN["legs"][0]["service_no"] = "ICE 107"
THIRD_TRAIN = copy.deepcopy(SECOND_TRAIN)
THIRD_TRAIN["price_amount"] = "300.00"
THIRD_TRAIN["legs"][0]["service_no"] = "ICE 109"
BOX = "document.querySelector('#trip-summary textarea')"


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
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id,
           [FLIGHT, CHEAP_TRAIN, SECOND_TRAIN, THIRD_TRAIN])
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


def _no_dialog(page):
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    return dialogs


@pytest.mark.parametrize("width", [1280, 390])
def test_a_click_puts_the_3_lines_on_the_clipboard(live, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        context = browser.new_context(viewport={"width": width, "height": 900},
                                      permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        dialogs = _no_dialog(page)
        page.goto(live)
        expected = page.evaluate(f"{BOX}.value")
        assert len(expected.split("\n")) == 3 and "€300.00" not in expected
        page.get_by_role("button", name="Copy summary").click()
        wait_js(page, "document.querySelector('#trip-summary [role=status]').textContent === 'Copied'")
        assert wait_js(page, "navigator.clipboard.readText()") == expected
        assert page.evaluate(f"{BOX}.hidden") and not dialogs
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        browser.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_with_no_clipboard_api_the_click_shows_the_text_selected(live, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        context = browser.new_context(viewport={"width": width, "height": 900})
        context.add_init_script("delete Navigator.prototype.clipboard")
        page = context.new_page()
        dialogs = _no_dialog(page)
        page.goto(live)
        assert page.evaluate("navigator.clipboard") is None
        page.get_by_role("button", name="Copy summary").click()
        wait_js(page, f"!{BOX}.hidden")
        text = page.evaluate(f"{BOX}.value")
        assert len(text.split("\n")) == 3
        assert page.evaluate(f"{BOX}.selectionStart === 0 && {BOX}.selectionEnd === {BOX}.value.length")
        assert page.evaluate(f"document.activeElement === {BOX}") and not dialogs
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        browser.close()


def test_a_change_of_the_hour_markup_changes_the_copied_text(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        context = browser.new_context(viewport={"width": 1280, "height": 900},
                                      permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.goto(live)
        assert "€40.00" in page.evaluate(f"{BOX}.value.split('\\n')[0]") # the cheap train first at 0 per hour
        page.evaluate("window.marker = 1; document.querySelectorAll('details.panel-toggle, details.advanced')"
                      ".forEach(d => d.open = true)")
        page.locator("form.weights input[name=hour_markup]").fill("20")
        wait_js(page, f"{BOX}.value.split('\\n')[0].includes('€60.00')")  # the flight of 2 h is best now
        page.get_by_role("button", name="Copy summary").click()
        assert wait_js(page, "navigator.clipboard.readText()").split("\n")[0].startswith(
            page.evaluate(f"{BOX}.value.split('\\n')[0]"))
        assert page.evaluate("window.marker") == 1  # no reload
        browser.close()
