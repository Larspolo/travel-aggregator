"""The "More" menu of the trip page opens inside the screen, on a phone and on a desktop (#746)."""

import os

import pytest

from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 480, 560, 640, 800, 1024, 1280])
def test_the_more_menu_opens_inside_the_screen(live, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(live)
        page.wait_for_selector("#rows > tr:not(.detail)")
        page.locator("details.more > summary").click()
        menu = page.locator(".more-menu")
        menu.wait_for(state="visible")
        box = menu.bounding_box()
        browser.close()
    assert box["x"] >= 0, f"the menu starts left of the screen at x={box['x']}"
    assert box["x"] + box["width"] <= width, f"the menu ends right of the screen at {box['x'] + box['width']}"
