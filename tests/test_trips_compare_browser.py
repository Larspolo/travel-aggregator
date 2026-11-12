"""The compare-trips page (#2555): select trips on the trips list, compare them, no sideways scroll at 390 px."""

import pytest

from tests.test_a11y_browser import launch
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)
from tests.test_trips_compare_page import add_trip

pytestmark = pytest.mark.slow


def test_compare_two_trips_from_the_list_at_390_px(live, days_trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sessions() as s:
        a = add_trip(s, "Amsterdam → Berlin 2026-12-20 long title", "Berlin", "82.40")
        b = add_trip(s, "Amsterdam → Paris 2026-12-20 long title", "Paris", "97.00")
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live.rsplit("/trips/", 1)[0] + "/")
        page.check(f'input[name="id"][value="{a}"]')
        page.check(f'input[name="id"][value="{b}"]')
        page.get_by_role("button", name="Compare trips").click()
        page.wait_for_url("**/trips/compare?*")
        best = page.locator("td.cost.best").inner_text()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        browser.close()
    assert "effective €97.40" in best
    assert scroll <= 390, f"the compare-trips page at 390 px scrolls sideways: {scroll} px"
