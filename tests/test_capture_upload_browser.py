"""The captures page of a trip, with the form "Upload a payload", has no sideways scroll and no serious or critical
axe-core finding at 390 and 1280 px (#1340, epic #1298)."""

from datetime import datetime, timezone

import pytest

from tests.test_a11y_browser import launch, serious
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 1280])
def test_the_capture_upload_form_fits_the_screen_and_has_no_axe_finding(live, days_trip, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from app.models import Capture

    with sessions() as s:
        s.add(Capture(trip_id=days_trip, source="bahn.de", captured_at=datetime(2026, 11, 3, tzinfo=timezone.utc)))
        s.commit()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        response = page.goto(live.rsplit("/trips/", 1)[0] + f"/trips/{days_trip}/captures")
        page.wait_for_load_state("networkidle")
        form = page.locator("#upload-payload form").count()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        found = serious(page)
        browser.close()
    assert response.status == 200
    assert form == 1, "the upload form is missing"
    assert scroll <= width, f"the captures page at {width} px scrolls sideways: {scroll} px"
    assert not found, f"the captures page at {width} px: axe findings {sorted(found)}"
