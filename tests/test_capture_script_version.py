"""The source table of the captures page warns about an old userscript (#1495, epic #1493)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.web.userscripts import served_versions
from tests.test_a11y_browser import launch, serious
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

PASSWORD = "pw"
T0 = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)
SERVED = served_versions()["bahn.de"]


def _seed(sessions, newest_version, trip_id=None):
    with sessions() as s:
        if trip_id is None:
            trip = Trip(title="Reise")
            s.add(trip)
            s.flush()
            trip_id = trip.id
        s.add_all([Capture(trip_id=trip_id, source="bahn.de", parser_version=SERVED, captured_at=T0, offer_count=3,
                           rejected_count=0),
                   Capture(trip_id=trip_id, source="bahn.de", parser_version=newest_version,
                           captured_at=T0 + timedelta(hours=1), offer_count=0, unreadable="no JSON")])
        s.commit()


def _bahn_row(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    html = c.get("/captures").text
    return re.search(r'<tr class="source-row"><td class="source-name">bahn.de(.*?)</tr>', html, re.S).group(1)


def test_an_old_newest_capture_shows_the_warning(sessions, monkeypatch):
    _seed(sessions, "1.1.0")
    row = _bahn_row(monkeypatch)
    assert f'<a class="chip warn" href="/tokens">old userscript 1.1.0: update to {SERVED}</a>' in row


@pytest.mark.parametrize("version", [SERVED, None])
def test_a_served_or_unknown_version_shows_no_warning(sessions, monkeypatch, version):
    _seed(sessions, version)
    assert "old userscript" not in _bahn_row(monkeypatch)


@pytest.mark.slow
@pytest.mark.parametrize("width", [390, 1280])
def test_the_warning_fits_the_screen_and_has_no_axe_finding(live, days_trip, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    _seed(sessions, __import__("os").environ.get("V", "1.1.0"), days_trip)
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(live.rsplit("/trips/", 1)[0] + "/captures")
        page.wait_for_load_state("networkidle")
        chips = page.locator("#source-health .chip.warn").count()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        inner = page.evaluate("(() => { const e = document.querySelector('#source-health .scroll');"
                              " return e.scrollWidth - e.clientWidth; })()")
        found = serious(page)
        browser.close()
    assert chips == 1
    assert scroll <= width, f"the captures page at {width} px scrolls sideways: {scroll} px"
    assert inner <= 0, f"the source table at {width} px scrolls sideways: {inner} px"
    assert not found, f"the captures page at {width} px: axe findings {sorted(found)}"
