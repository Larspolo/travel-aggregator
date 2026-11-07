"""The journey box is a timeline: one row per part, its cost at the right, no horizontal scroll (#663)."""

import os
from pathlib import Path

import pytest

from tests.test_mobile_whole import DESKTOP, PHONE, _launch
from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_journey import _late
from tests.test_trip_next import _next
from tests.test_trip_page import BODY, ingest, offer

STATIC = Path(__file__).resolve().parent.parent / "app" / "web" / "static"


@pytest.mark.slow
def test_a_three_part_journey_is_one_row_per_part_at_1280_and_390(setup, sessions, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    c, auth, first = setup
    second = _next(c, first)
    third = _next(c, second)
    ingest(c, auth, first, [offer("89.90", "ICE 105")])
    ingest(c, auth, second, [_late("50.00", "ICE 900")])
    ingest(c, auth, third, [_late("30.00", "ICE 901", day=BODY["offers"][0]["legs"][0]["depart_at"][:10])])
    html = c.get(f"/trips/{first}").text
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        for width in (DESKTOP, PHONE):
            page = browser.new_page(viewport={"width": width, "height": 800}, device_scale_factor=2)
            page.route("**/static/**", lambda r: r.fulfill(path=str(STATIC / r.request.url.split("/static/")[1])))
            page.goto("http://test.local/static/app.css")
            page.set_content(html)
            box = page.locator("section.journey")
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            parts = box.locator("li.journey-part")
            assert parts.count() == 3
            for i in range(3):
                row, cost = parts.nth(i).bounding_box(), parts.nth(i).locator(".journey-cost").bounding_box()
                assert abs((row["x"] + row["width"]) - (cost["x"] + cost["width"])) < 2
            assert box.locator(".chip.warn").count() == 1
            box.screenshot(path=f"{shots}/journey-{width}.png")
            page.close()
