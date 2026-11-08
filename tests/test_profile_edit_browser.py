"""The profile page (#1013) fits the screen at 390 px and 1280 px, also with "Advanced" open."""

import os

import pytest

from tests.test_pages_width_browser import OUTSIDE
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 1280])
def test_profile_form_has_no_sideways_scroll(live, days_trip, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base = live.rsplit("/trips/", 1)[0]
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        status = page.goto(base + "/profiles/new").status
        page.click("details.advanced > summary")
        scroll = page.evaluate("document.documentElement.scrollWidth")
        outside = page.evaluate(OUTSIDE, width)
        shots = os.environ.get("SCREENSHOT_DIR")
        if shots:
            page.screenshot(path=os.path.join(shots, f"profile-new-{width}.png"), full_page=True)
        browser.close()
    assert status == 200
    assert scroll <= width, f"scrolls sideways: {scroll} px"
    assert not outside, f"elements outside the screen: {outside[:5]}"
