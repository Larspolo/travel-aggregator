"""The series page (#2500) has no sideways scroll at 390 px."""

import pytest

from tests.test_a11y_browser import launch
from tests.test_series_page import _series
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


def test_series_page_has_no_sideways_scroll_at_390_px(live, days_trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    sid, _ = _series(sessions.kw["bind"])
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live.rsplit("/trips/", 1)[0] + f"/series/{sid}")
        lines = page.locator("li.series-trip").count()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        browser.close()
    assert lines == 4
    assert scroll <= 390, f"the series page at 390 px scrolls sideways: {scroll} px"
