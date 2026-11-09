"""The "Pinned" page with pinned rows has no sideways scroll and no serious or critical axe-core finding at 390 and
1280 px (#1332, epic #1298)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.test_a11y_browser import launch, serious
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 1280])
def test_the_pinned_page_fits_the_screen_and_has_no_axe_finding(live, days_trip, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select

    from app.models import Fare, FarePrice, Itinerary

    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == days_trip).order_by(Itinerary.id)).all()
        for it in its[:2]:
            it.pinned = True
        fare = s.scalars(select(Fare).where(Fare.itinerary_id == its[0].id)).first()
        s.add(FarePrice(fare_id=fare.id, price=fare.latest_price - Decimal("20.00"), currency=fare.currency,
                        captured_at=fare.latest_captured_at - timedelta(days=1)))
        s.commit()
    base = live.rsplit("/trips/", 1)[0]
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        response = page.goto(base + "/pinned")
        page.wait_for_load_state("networkidle")
        rows = page.locator("ol.pinned > li").count()
        text = page.inner_text("main")
        scroll = page.evaluate("document.documentElement.scrollWidth")
        found = serious(page)
        browser.close()
    assert response.status == 200
    assert rows == 2, f"{rows} pinned rows"
    assert "now" in text and "above" in text, text
    assert scroll <= width, f"/pinned at {width} px scrolls sideways: {scroll} px"
    assert not found, f"/pinned at {width} px: axe findings {sorted(found)}"
