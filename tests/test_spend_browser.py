"""The page "Travel per year" (/upcoming/years) has no sideways scroll and no serious or critical axe-core finding at
390 and 1280 px, and it shows a year card for a booked journey (#1365, epic #1352)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.test_a11y_browser import launch, serious
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [390, 1280])
def test_the_years_page_fits_the_screen_and_has_no_axe_finding(live, days_trip, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from app.models import Itinerary, Leg, Trip

    depart = datetime(2026, 12, 18, 8, tzinfo=timezone.utc)
    arrive = depart + timedelta(minutes=600)
    leg = Leg(seq=0, mode="train", carrier="ICE", service_no="201", from_name="Amsterdam", to_name="Zürich",
              depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    with sessions() as s:
        trip = s.get(Trip, days_trip)
        trip.itineraries.append(Itinerary(fingerprint="spend-browser", depart_at=depart, arrive_at=arrive,
                                          duration_min=600, booked=True, booked_price=Decimal("100.00"),
                                          booked_currency="EUR", legs=[leg]))
        s.commit()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        response = page.goto(live.rsplit("/trips/", 1)[0] + "/upcoming/years")
        page.wait_for_load_state("networkidle")
        cards = page.locator("section.year-summary").count()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        found = serious(page)
        browser.close()
    assert response.status == 200
    assert cards >= 1, "the years page shows no year card"
    assert scroll <= width, f"the years page at {width} px scrolls sideways: {scroll} px"
    assert not found, f"the years page at {width} px: axe findings {sorted(found)}"
