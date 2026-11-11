"""The expanded best row with its hour range fits a 390 px phone screen: no sideways scroll (#1937)."""

import os

import pytest

from tests.test_compare_tradeoff import timed
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow


def test_the_expanded_best_row_fits_390_px(live, days_trip, sessions):  # noqa: F811
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright

    from app import tokens
    from app.main import app

    with sessions() as s:
        token = tokens.create(s, "test-range")
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, days_trip,
           [timed("30.00", 1, "ICE 1"), timed("20.00", 3, "ICE 2")])
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live + "?hour_markup=20")
        page.wait_for_load_state("networkidle")
        line = page.locator("p.best-range").first
        line.locator("xpath=ancestor::details[1]/summary").click()
        line.wait_for(state="visible")
        widths = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        browser.close()
    assert widths[0] <= widths[1], f"the page scrolls sideways: {widths}"
