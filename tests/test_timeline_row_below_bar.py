"""A click on a timeline bar shows the whole row below the sticky top bar, and the time label stays readable (#946)."""

import os

import pytest

from tests.test_trip_page import trip  # noqa: F401  (a fixture)
from tests.test_trip_timeline_browser import _browser, live  # noqa: F401  (a fixture)

pytestmark = pytest.mark.slow


def test_the_row_of_a_bar_starts_below_the_top_bar(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    url, _, second = live
    with sync_playwright() as p:
        browser = _browser(p)
        for width in (1280, 390):
            # A low window: the page must scroll to the row.
            page = browser.new_page(viewport={"width": width, "height": 420})
            page.goto(url)
            page.click("#trip-timeline summary")
            label = page.locator(f'.timeline-bar[href="#it-{second}"] .tl-text')
            assert page.evaluate("e => getComputedStyle(e).backgroundColor", label.element_handle()) \
                not in ("rgba(0, 0, 0, 0)", "transparent")
            page.click(f'.timeline-bar[href="#it-{second}"]')
            page.wait_for_function(f"document.getElementById('it-{second}').nextElementSibling"
                                   ".querySelector('details').open")
            page.wait_for_timeout(300)
            if os.environ.get("SHOTS"):  # the screenshots of the PR
                page.screenshot(path=os.path.join(os.environ["SHOTS"], f"row-{width}.png"))
            row_top = page.evaluate(f"document.getElementById('it-{second}').getBoundingClientRect().top")
            bar_bottom = page.evaluate("document.querySelector('nav.topbar').getBoundingClientRect().bottom")
            assert page.evaluate("window.scrollY") > 0
            assert row_top >= bar_bottom, (width, row_top, bar_bottom)
            page.close()
        browser.close()
