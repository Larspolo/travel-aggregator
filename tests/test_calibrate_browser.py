"""The hour value of the bookings on the profile page in a browser, at 390 px and 1280 px (#1711)."""

import os
from decimal import Decimal

import pytest

from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_calibrate_page import two_bookings
from tests.test_pages_width_browser import OUTSIDE
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 1280])
def test_use_this_hour_value_sets_the_field(live, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    two_bookings(sessions)
    with sessions() as s:
        p = ScoreProfile(name="Mine", config_json=to_config(Weights(hour_markup=Decimal("10"))))
        s.add(p)
        s.commit()
        pid = p.id
    base = live.rsplit("/trips/", 1)[0]
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe) if os.path.exists(exe) else pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(f"{base}/profiles/{pid}")
        text = page.inner_text(".hour-fit")
        page.click("text=Use this hour value")
        page.wait_for_function("document.getElementById('hour_markup').value === '30.00'")
        scroll = page.evaluate("document.documentElement.scrollWidth")
        outside = page.evaluate(OUTSIDE, width)
        shots = os.environ.get("SCREENSHOT_DIR")
        if shots:
            page.screenshot(path=os.path.join(shots, f"profile-hour-value-{width}.png"), full_page=True)
        browser.close()
    assert text == "Your bookings fit an hour value from €20 to €40 (2 of 2 bookings)"
    assert scroll <= width and not outside
