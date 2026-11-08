"""The split tickets section at 1280 and 390 px: no sideways scroll and no serious axe finding (#1179)."""

import os

import pytest

from app.models import Trip
from tests.test_a11y_browser import launch, serious
from tests.test_mobile_width import live  # noqa: F401  (fixture: the live server)
from tests.test_split_page import _offer
from tests.test_trip_page import trip  # noqa: F401  (fixture)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [1280, 390])
def test_the_split_section_fits_and_has_no_axe_finding(live, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, trip_id, _ = live
    with sessions() as s:
        parent = s.get(Trip, trip_id)
        parts = [Trip(title=f"{a} → {b}", origin_text=a, destination_text=b, split_of_id=trip_id)
                 for a, b in (("Amsterdam Centraal", "Köln Hbf"), ("Köln Hbf", "Zürich HB"))]
        s.add_all(parts)
        s.flush()
        parent.origin_text = "Amsterdam Centraal"
        _offer(s, parts[0].id, "Amsterdam Centraal", "Köln Messe/Deutz", 0, 3, "40", "ns")
        _offer(s, parts[1].id, "Köln Messe/Deutz", "Zürich HB", 4, 5, "50", "db")
        s.commit()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_load_state("networkidle")
        assert page.locator(".split-section").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        found = serious(page)
        shots = os.environ.get("SHOT_DIR")
        if shots:
            page.locator(".split-section").screenshot(path=f"{shots}/split-{width}.png")
        browser.close()
    assert found == set()
