"""The trip cards fit 1280 px and 390 px in light and dark mode (#626)."""

import os

import pytest

from tests.test_mobile_whole import DESKTOP, PHONE, _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow


def test_the_cards_fit_both_widths(live, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, _ = live
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))  # CI uploads them as the artifact "screenshots"
    os.makedirs(shots, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                page = browser.new_page(viewport={"width": width, "height": 800}, color_scheme=scheme,
                                        device_scale_factor=2)
                page.goto(f"{base}/")
                assert page.locator(".trip-grid .card").count() >= 1
                assert page.evaluate("document.documentElement.scrollWidth") <= width
                page.screenshot(path=f"{shots}/trips-{width}-{scheme}.png", full_page=True)
                page.close()
        browser.close()
