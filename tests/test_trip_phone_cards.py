"""On a phone each itinerary is a card; the weights panel is closed; a computer keeps the table (#593)."""

import pytest

from tests.test_mobile_touch import PHONE, _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import trip  # noqa: F401

pytestmark = pytest.mark.slow

CARD = "#table tbody tr:not(.detail)"


def test_a_phone_shows_cards_and_a_tap_opens_the_details(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, tid = live
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_context(**p.devices[PHONE]).new_page()
        page.goto(f"{base}/trips/{tid}")
        width = page.viewport_size["width"]
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert not page.locator(".panel-toggle").evaluate("e => e.open")
        assert not page.locator("form.weights input[name=hour_markup]").is_visible()
        assert not page.locator("#table thead").is_visible()
        card = page.locator(CARD).first
        assert card.evaluate("e => getComputedStyle(e).display") == "grid"
        box = card.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        text = card.inner_text()
        for part in ["→", "Sun 20 Dec", "€", "best value"]:
            assert part in text, part
        summary = page.locator("#table tr.detail summary").first
        summary.tap()
        page.wait_for_function("document.querySelector('#table tr.detail details').open", timeout=5000)
        assert page.locator("#table tr.detail .legs").first.is_visible()

        desk = browser.new_page(viewport={"width": 1280, "height": 800})
        desk.goto(f"{base}/trips/{tid}")
        assert desk.locator("form.weights input[name=hour_markup]").is_visible()
        assert not desk.locator(".panel-toggle > summary").is_visible()
        assert desk.locator("#table thead").is_visible()
        assert desk.locator(CARD).first.evaluate("e => getComputedStyle(e).display") == "table-row"
        panel, table = desk.locator("aside.panel").bounding_box(), desk.locator("#table").bounding_box()
        assert panel["x"] + panel["width"] <= table["x"]
        browser.close()
