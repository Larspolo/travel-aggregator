""""Save as profile" saves the weights of the form, also after a slider move (#301)."""

import os

import pytest

from tests.test_trip_sliders_browser import live  # noqa: F401  (a fixture)
from tests.test_trip_page import trip  # noqa: F401  (a fixture)

pytestmark = pytest.mark.slow


def test_save_as_profile_uses_the_moved_slider(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page()
        page.goto(live)
        page.locator("form.weights input[name=hour_markup]").fill("50")
        page.locator("details").filter(has=page.locator("input[name=name]")).locator("summary").click()
        page.locator("input[name=name]").fill("Fast")
        page.get_by_role("button", name="Save as profile").click()
        page.wait_for_load_state()
        page.goto(live.split("/trips/")[0] + "/profiles")
        assert "€50/h" in page.content()
        browser.close()
