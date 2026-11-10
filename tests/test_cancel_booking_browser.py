"""The trip page with a booked row (form "Cancel booking") and a cancelled row has no serious axe finding at 1280 and
390 px (#1686). SHOTS=<dir> saves the screenshots for the PR."""

import os
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.main import app
from app.models import Itinerary, Trip
from tests.test_a11y_browser import check, launch, serious
from tests.test_trip_alternatives_browser import BASEL, ROWS, ZURICH, server  # noqa: F401
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [1280, 390])
def test_cancel_form_and_cancelled_row_have_no_serious_axe_finding(server, sessions, width):  # noqa: F811
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright

    base, token = server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
        page.goto(f"{base}/trips/new")
        page.fill("input[name=title]", "Amsterdam – Zürich")
        page.fill("input[name=origin_text]", "Amsterdam")
        page.fill("input[name=destination_text]", "Zürich")
        page.fill("input[name=date_from]", "2026-12-20")
        page.click("form[action=\"/trips/new\"] button[type=submit]")
        page.wait_for_url(f"{base}/")
        with sessions() as s:
            trip_id = s.scalar(select(Trip.id).where(Trip.title == "Amsterdam – Zürich"))
        ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, [ZURICH, BASEL])
        with sessions() as s:
            it = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).first()
            it.booked, it.booked_price, it.booked_currency = True, Decimal("89"), "EUR"
            it.booked_fare_id = it.fares[0].id
            iid = it.id
            s.commit()
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        page.evaluate("document.querySelectorAll('#rows details').forEach(d => d.open = true)")
        assert page.locator(f"label[for=refund-{iid}]").inner_text() == "Refund"
        check("/trips/{id}", width, serious(page))
        shots = os.environ.get("SHOTS")
        if shots:
            page.locator(f"form[action$='/itineraries/{iid}/cancel']").scroll_into_view_if_needed()
            page.screenshot(path=f"{shots}/cancel-form-{width}.png")
        page.fill(f"#refund-{iid}", "60")
        with page.expect_navigation():
            page.locator(f"form[action$='/itineraries/{iid}/cancel'] button").click()
        page.wait_for_selector(ROWS)
        assert page.get_by_text("Booking cancelled: paid €89.00, refund €60.00").count() >= 1
        assert page.locator(".badge.booked").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        check("/trips/{id}", width, serious(page))
        if shots:
            page.screenshot(path=f"{shots}/cancelled-{width}.png")
        browser.close()
