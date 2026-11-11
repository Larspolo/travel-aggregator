""""Same journey" works by a tap on a phone at 390 px (#2145). No browser dialog fires (P6)."""

import pytest
from tests.test_mobile_controls import _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow


def test_two_taps_and_a_tap_on_same_journey_join_the_rows(live, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from app.models import Itinerary

    base, tid = live
    dialogs = []
    with sync_playwright() as p:
        browser = _launch(p)
        context = browser.new_context(viewport={"width": 390, "height": 800}, has_touch=True)
        page = context.new_page()
        page.on("dialog", lambda d: dialogs.append(d.message))
        page.goto(f"{base}/trips/{tid}")
        rows = page.locator("#table tbody tr:has(label.pick)").count()
        for i in range(2):
            page.locator("#table label.pick").nth(i).tap()
            page.wait_for_function(f"document.querySelectorAll('#table input[name=it]:checked').length === {i + 1}")
        button = page.locator(".compare-bar button", has_text="Same journey")
        assert button.is_visible()
        with page.expect_navigation():
            button.tap()
        assert "The 2 rows are joined into one row." in page.content()
        assert page.locator("#table tbody tr:has(label.pick)").count() == rows - 1
        with sessions() as s:
            assert s.query(Itinerary).filter(Itinerary.trip_id == tid, Itinerary.merged_into_id.is_not(None)).count() == 1
        assert dialogs == []
        context.close()
        browser.close()
