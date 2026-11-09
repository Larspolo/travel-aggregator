"""A click on "Split via Köln Hbf" makes the split trip, at desktop and phone width (#1461)."""

import pytest

from tests.test_a11y_browser import launch
from tests.test_mobile_width import live  # noqa: F401  (fixture: the live server)
from tests.test_split_suggest_page import _via
from tests.test_trip_page import ingest, trip  # noqa: F401  (fixture)

pytestmark = pytest.mark.slow

FITS = "document.documentElement.scrollWidth <= window.innerWidth"


@pytest.mark.parametrize("phone", [False, True])
def test_the_via_button_makes_the_split_trip(live, trip, phone):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, trip_id, _ = live
    client, auth, _ = trip
    ingest(client, auth, trip_id, [_via("ICE 901", "Köln Hbf"), _via("ICE 902", "Köln Hbf")])
    with sync_playwright() as p:
        browser = launch(p)
        if phone:
            context = browser.new_context(**p.devices["Pixel 7"])
        else:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(f"{base}/trips/{trip_id}")
        assert page.evaluate(FITS)
        page.get_by_role("link", name="Split the trip").click()
        page.wait_for_load_state("networkidle")
        button = page.get_by_role("button", name="Split via Köln Hbf")
        assert page.evaluate(FITS) and button.count() == 1
        button.click()
        page.wait_for_url(f"{base}/trips/{trip_id}*")
        page.get_by_role("heading", name="Split tickets via Köln Hbf").wait_for()
        assert page.evaluate(FITS)
        browser.close()
