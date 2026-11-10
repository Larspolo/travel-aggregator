"""The end date form of the share link works with a keyboard and at 390 px (#2040, epic #2025)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Trip
from app.share import new_link
from tests.test_keyboard_browser import open_page, tab_to
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


@pytest.fixture
def shared(live, sessions):  # noqa: F811
    with sessions() as s:
        new_link(s.scalars(select(Trip)).one())
        s.commit()
    return live


def _open_menu(page):
    tab_to(page, "details.more > summary")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelector('details.more').open")


@pytest.mark.parametrize("width", [390, 1280])
def test_the_keyboard_sets_the_end_date(shared, width):
    from playwright.sync_api import sync_playwright

    end = date.today() + timedelta(days=30)
    with sync_playwright() as p:
        browser, page = open_page(p, shared, width)
        _open_menu(page)
        tab_to(page, "#f-share-end")
        page.keyboard.type(end.strftime("%m%d%Y"))
        tab_to(page, "form[action$='/share/end'] button", limit=5)
        with page.expect_navigation():
            page.keyboard.press("Enter")
        text = page.locator("p.share-ends").text_content()
        browser.close()
    assert text == f"Ends on {end.isoformat()}"


def test_the_form_fits_at_390_px(shared):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = open_page(p, shared, 390)
        _open_menu(page)
        boxes = [page.locator(s).bounding_box() for s in ("#f-share-end", "form[action$='/share/end'] button")]
        scroll = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        browser.close()
    for box in boxes:
        assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 390, box
    assert scroll <= 0
