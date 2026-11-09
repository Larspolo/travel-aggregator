"""The service worker deletes the saved Upcoming page when the server sends the login page (#1267)."""

import os

import pytest

from tests.browser_wait import wait_js
from tests.test_upcoming_offline import CACHED, live, login  # noqa: F401

pytestmark = pytest.mark.slow


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        yield b
        b.close()


def _save_upcoming(page, live):  # noqa: F811
    login(page, live)
    page.goto(live + "/upcoming")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")


def test_a_session_ended_on_another_device_deletes_the_saved_page(live, browser):  # noqa: F811
    one, two = browser.new_context().new_page(), browser.new_context().new_page()
    login(one, live)
    _save_upcoming(two, live)
    one.goto(live + "/settings")
    one.click("text=Log out on all other devices")
    one.wait_for_load_state()
    assert "All other devices are logged out." in one.inner_text("body")
    two.goto(live + "/")
    assert "/login" in two.url
    wait_js(two, f"{CACHED}.then(p => !p.includes('/upcoming'))")
    two.context.set_offline(True)
    two.goto(live + "/upcoming")
    body = two.inner_text("body")
    assert "No saved journeys" in body and "Amsterdam" not in body and "Offline trip" not in body


def test_a_normal_visit_keeps_the_saved_page(live, browser):  # noqa: F811
    page = browser.new_context().new_page()
    _save_upcoming(page, live)
    page.goto(live + "/")
    page.goto(live + "/upcoming")
    page.wait_for_load_state()
    assert "/upcoming" in page.evaluate(CACHED)
    page.context.set_offline(True)
    page.reload()
    assert "Amsterdam → Berlin" in page.inner_text("body")
