"""The Upcoming page makes and revokes the calendar link (#1113)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
import tests.test_upcoming_offline as offline
from tests.browser_wait import wait_js
from tests.test_upcoming_offline import CACHED, login
from tests.test_upcoming_page import client  # noqa: F401  (a fixture)

live = offline.live  # the fixtures of the Upcoming offline tests
page = offline.page


def _csrf(c) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/upcoming").text).group(1)


def test_subscribe_shows_the_link_once_and_revoke_stops_it(client):  # noqa: F811
    assert "No calendar link" in client.get("/upcoming").text
    r = client.post("/upcoming/calendar", data={"csrf_token": _csrf(client)})
    assert "Subscribed since" in r.text and "Revoke" in r.text
    link = re.search(r'value="(http[^"]+/calendar/[^"]+\.ics)"', r.text).group(1)
    assert "webcal://" + link.split("://", 1)[1] in r.text
    path = link.split("testserver", 1)[1]
    assert TestClient(app).get(path).status_code == 200
    again = client.get("/upcoming").text
    assert link not in again and "Subscribed since" in again
    r = client.post("/upcoming/calendar/revoke", data={"csrf_token": _csrf(client)})
    assert "No calendar link" in r.text
    assert TestClient(app).get(path).status_code == 404


@pytest.mark.parametrize("path", ["/upcoming/calendar", "/upcoming/calendar/revoke"])
def test_the_forms_need_the_login_and_the_csrf_token(client, path):  # noqa: F811
    assert client.post(path, data={"csrf_token": "bad"}, follow_redirects=False).status_code in (400, 403)
    anon = TestClient(app)
    assert anon.post(path, data={"csrf_token": "x"}, follow_redirects=False).status_code in (303, 401, 403)
    assert "Subscribed since" not in client.get("/upcoming").text


@pytest.mark.slow
def test_the_link_fits_390_px_and_the_offline_copy_has_no_link(live, page):
    login(page, live)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live + "/upcoming")
    page.click("text=Subscribe in a calendar")
    page.wait_for_selector("input.share-link")
    assert page.get_attribute("a[href^='webcal://']", "href").endswith(".ics")
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")
    cached = page.evaluate("caches.open('upcoming-v1').then(c => c.match('/upcoming')).then(r => r ? r.text() : '')")
    assert ".ics" in page.content() and "webcal://" not in cached and "share-link" not in cached
