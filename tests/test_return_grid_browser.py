"""The grid of a round trip in a real browser (#1108): no horizontal scroll at 390 px, no serious axe-core finding."""

import os
from datetime import date

import pytest

from tests.test_a11y_browser import launch, serious
from tests.test_trip_days_browser import days_trip, live, offer_on  # noqa: F401  (fixtures: the trip and the server)
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow


@pytest.fixture
def back_trip(live, days_trip, sessions):  # noqa: F811
    from fastapi.testclient import TestClient

    from app import tokens
    from app.main import app
    from app.models import Trip

    with sessions() as s:
        token = tokens.create(s, "test-back")
        t = Trip(title="Zürich – Amsterdam", origin_text="Zürich", destination_text="Amsterdam",
                 date_from=date(2026, 12, 23), date_to=date(2026, 12, 27), return_of_id=days_trip)
        s.add(t)
        s.commit()
        back_id = t.id
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, back_id,
           [offer_on("70.00", "2026-12-24", "ICE 601"), offer_on("95.00", "2026-12-26", "ICE 701")])
    return back_id


@pytest.mark.parametrize("width", [1280, 390])
def test_the_grid_fits_and_has_no_serious_axe_finding(live, days_trip, back_trip, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base = live.rsplit("/trips/", 1)[0]
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        for tid in (days_trip, back_trip):
            page.goto(f"{base}/trips/{tid}")
            page.wait_for_load_state("networkidle")
            assert page.locator("#return-grid td.best a").count() == 1
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            assert not serious(page), f"trip {tid} at {width} px"
            shots = os.environ.get("GRID_SHOTS")
            if shots:
                page.locator("#return-grid").screenshot(path=f"{shots}/grid-{tid}-{width}.png")
        page.goto(f"{base}/trips/{days_trip}")
        page.locator("#return-grid td.best a").click()
        page.wait_for_load_state("networkidle")
        assert "day=2026-12-19" in page.url  # the best sum: the €60 outbound day
        browser.close()
