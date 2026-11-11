"""The keys panel of the trip page: "?" and the "Keys" button open it, Escape closes it (#2439)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Trip
from tests.test_a11y_browser import launch
from tests.test_trip_alternatives_browser import ROWS, _offer, server  # noqa: F401
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow

OPEN = "document.getElementById('keys').matches(':popover-open')"


def _trip_page(server, sessions):  # noqa: F811
    base, token = server
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id,
           [_offer(f"ICE {n}", "Zürich HB", f"{80 + n}.00") for n in range(2)])
    return base, trip_id


def test_question_mark_and_the_button_open_the_panel_and_escape_closes_it(server, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, trip_id = _trip_page(server, sessions)
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        assert page.evaluate(OPEN) is False
        page.keyboard.press("?")
        assert page.evaluate(OPEN) is True
        assert page.locator("#keys dt").count() == 4
        page.keyboard.press("Escape")
        assert page.evaluate(OPEN) is False
        page.click("button[popovertarget=keys]")
        assert page.evaluate(OPEN) is True
        browser.close()


def test_question_mark_in_a_form_field_opens_no_panel(server, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, trip_id = _trip_page(server, sessions)
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        page.focus("input[name=hour_markup]")
        page.keyboard.press("?")
        assert page.evaluate(OPEN) is False
        browser.close()


def test_the_panel_fits_a_phone_width(server, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, trip_id = _trip_page(server, sessions)
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        page.click("button[popovertarget=keys]")
        box = page.locator("#keys").bounding_box()
        assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 390
        browser.close()
