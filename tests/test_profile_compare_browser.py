"""The "Best by profile" section of the trip page (#1211) fits the screen at 390 px and 1280 px."""

import os
from decimal import Decimal

import pytest

from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_pages_width_browser import OUTSIDE
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 1280])
def test_best_by_profile_has_no_sideways_scroll(live, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("2")))))
        s.add(ScoreProfile(name="Comfort with a long profile name", config_json=to_config(Weights(hour_markup=Decimal("30")))))
        s.commit()
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        status = page.goto(live).status
        lines = page.locator("#profile-best li").count()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        outside = page.evaluate(OUTSIDE, width)
        shots = os.environ.get("SCREENSHOT_DIR")
        if shots:
            page.locator("#profile-best").screenshot(path=os.path.join(shots, f"profile-best-{width}.png"))
        page.click("#profile-best li:nth-child(2) a")
        page.wait_for_url("**profile=*")
        active = page.locator("#profile-best li:nth-child(2)").inner_text()
        browser.close()
    assert status == 200 and lines == 2
    assert scroll <= width, f"scrolls sideways: {scroll} px"
    assert not outside, f"elements outside the screen: {outside[:5]}"
    assert "(active)" in active
