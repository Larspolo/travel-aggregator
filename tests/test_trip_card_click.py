"""A click anywhere on a trip card of the trips list opens the trip; the edit button still opens the edit form (#736)."""

import pytest
from playwright.sync_api import sync_playwright

from tests.test_mobile_width import live  # noqa: F401  (fixture)
from tests.test_trip_page import trip  # noqa: F401  (fixture)


def _click_at(page, selector):
    """Click the centre of the element as a person does: the title link covers the card on purpose."""
    box = page.locator(selector).first.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


@pytest.mark.slow
def test_a_click_on_the_card_opens_the_trip_and_edit_still_works(live):  # noqa: F811
    base, trip_id, _ = live
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base + "/")
        _click_at(page, ".trip-grid .card .trip-route")  # not the title: the point of a real tap
        page.wait_for_url(f"{base}/trips/{trip_id}")
        page.goto(base + "/")
        _click_at(page, ".trip-grid .card .trip-best")
        page.wait_for_url(f"{base}/trips/{trip_id}")
        page.goto(base + "/")
        _click_at(page, ".trip-grid .card .trip-card-head .btn-icon")
        page.wait_for_url(f"{base}/trips/{trip_id}/edit")
        browser.close()
