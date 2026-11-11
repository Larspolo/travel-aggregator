"""The trip page with all row details open has no serious axe finding at 1280 and 390 px (#1442: link-in-text-block
of a link in running text with no underline)."""

import pytest
from sqlalchemy import select

from app.main import app
from app.models import Trip
from tests.test_a11y_browser import check, launch, serious
from tests.test_trip_alternatives_browser import BASEL, ROWS, ZURICH, server  # noqa: F401
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("width", [1280, 390])
def test_open_row_details_have_no_serious_axe_finding(server, sessions, width):  # noqa: F811
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright

    base, token = server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(f"{base}/trips/new")
        page.fill("input[name=title]", "Amsterdam – Zürich")
        page.fill("input[name=origin_text]", "Amsterdam")
        page.fill("input[name=destination_text]", "Zürich")
        page.fill("input[name=destination_alt_text]", "Basel")
        page.fill("input[name=date_from]", "2026-12-20")
        page.click("form[action=\"/trips/new\"] button[type=submit]")
        page.wait_for_url(f"{base}/")
        with sessions() as s:
            trip_id = s.scalar(select(Trip.id).where(Trip.title == "Amsterdam – Zürich"))
        page.goto(f"{base}/places")
        page.fill("#place_text", "Basel SBB")
        page.select_option("#kind", "egress")
        page.fill("#minutes", "40")
        page.fill("#cost", "5")
        with page.expect_navigation():
            page.locator("form:has(#place_text) button[type=submit]").click()
        ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id, [ZURICH, BASEL])
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        page.evaluate("document.querySelectorAll('#rows details').forEach(d => d.open = true)")
        check("/trips/{id}", width, serious(page))
        browser.close()
