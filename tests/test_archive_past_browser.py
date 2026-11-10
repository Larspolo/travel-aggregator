"""The line "N trips are in the past" and its button work at 390 px with no sideways scroll and with a keyboard (#1998)."""

from datetime import date, timedelta

import pytest

from tests.test_a11y_browser import launch
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


def test_archive_them_works_at_390_px_with_the_keyboard(live, days_trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from app.models import Trip

    with sessions() as s:
        s.add(Trip(title="Old trip", origin_text="A", destination_text="B", date_from=date.today() - timedelta(days=20)))
        s.commit()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live.rsplit("/trips/", 1)[0] + "/")
        line = page.locator("form.trip-past")
        assert "1 trip is in the past." in line.inner_text()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        button = line.get_by_role("button", name="Archive them")
        button.focus()
        assert page.evaluate("document.activeElement.textContent.trim()") == "Archive them"
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        after = page.locator("form.trip-past").count()
        browser.close()
    assert scroll <= 390, f"the trips list at 390 px scrolls sideways: {scroll} px"
    assert after == 0
    with sessions() as s:
        assert s.query(Trip).filter_by(title="Old trip").one().status == "archived"
