"""The offline copy of the Upcoming page never holds the calendar link (#1407)."""

import re
import time

import pytest

from tests.browser_wait import wait_js
from tests.test_upcoming_offline import CACHED, live, login, page  # noqa: F401  (fixtures)
from tests.test_upcoming_page import client  # noqa: F401  (a fixture)

COPY = "caches.open('upcoming-v1').then(c => c.match('/upcoming')).then(r => r ? r.text() : '')"


def _csrf(c) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/upcoming").text).group(1)


def test_only_the_page_with_the_link_has_no_store(client):  # noqa: F811
    assert "no-store" not in client.get("/upcoming").headers.get("cache-control", "")
    r = client.post("/upcoming/calendar", data={"csrf_token": _csrf(client)})
    assert "share-link" in r.text and r.headers["cache-control"] == "no-store"
    again = client.get("/upcoming")
    assert "share-link" not in again.text and "no-store" not in again.headers.get("cache-control", "")


@pytest.mark.slow
def test_the_worker_does_not_save_the_page_with_the_link(live, page):  # noqa: F811
    login(page, live)
    page.goto(live + "/upcoming")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")
    wait_js(page, "!!navigator.serviceWorker.controller")
    before = page.evaluate(COPY)
    # no "save-upcoming" message from offline.js: only the navigation can change the copy
    page.context.add_init_script("ServiceWorker.prototype.postMessage = () => {};")
    page.click("text=Subscribe in a calendar")
    page.wait_for_selector("input.share-link")
    end = time.monotonic() + 2
    while time.monotonic() < end:
        copy = page.evaluate(COPY)
        assert "webcal://" not in copy and "share-link" not in copy
        time.sleep(0.1)
    assert page.evaluate(COPY) == before
