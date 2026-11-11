"""The bulk row actions of the compare bar (#1897, #1898) work with a keyboard and on a phone at 390 px (#1899).
No browser dialog fires (P6)."""

import pytest
from tests.test_mobile_controls import _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

PHONE = 390


def _tab_until(page, script, limit=1000):
    """Press Tab until the focused element matches `script`; the page order decides the number of presses."""
    for _ in range(limit):
        if page.evaluate(f"({script})(document.activeElement)"):
            return
        page.keyboard.press("Tab")
    raise AssertionError("the focus did not reach the element")


def test_keyboard_ticks_two_rows_and_enter_on_hide_hides_them(live, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from app.models import Itinerary

    base, tid = live
    dialogs = []
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("dialog", lambda d: dialogs.append(d.message))
        page.goto(f"{base}/trips/{tid}")
        for _ in range(2):  # Tab to an unticked row box, then Space ticks it
            _tab_until(page, "el => el.matches('#table input[name=it]') && !el.checked")
            page.keyboard.press("Space")
        assert page.locator("#table input[name=it]:checked").count() == 2
        _tab_until(page, "el => el.tagName === 'BUTTON' && (el.getAttribute('formaction') || '').endsWith('action=hide')")
        with page.expect_navigation():
            page.keyboard.press("Enter")
        with sessions() as s:
            hidden = s.query(Itinerary).filter(Itinerary.trip_id == tid, Itinerary.hidden.is_(True)).count()
        assert hidden == 2
        assert dialogs == []
        browser.close()


def test_a_tap_on_a_phone_ticks_a_row_and_the_bar_buttons_are_in_view(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, tid = live
    dialogs = []
    with sync_playwright() as p:
        browser = _launch(p)
        context = browser.new_context(viewport={"width": PHONE, "height": 800}, has_touch=True)
        page = context.new_page()
        page.on("dialog", lambda d: dialogs.append(d.message))
        page.goto(f"{base}/trips/{tid}")
        page.locator("#table label.pick").nth(0).tap()
        # a tap returns before the click of the gesture: wait for its result (#508)
        page.wait_for_function("document.querySelectorAll('#table input[name=it]:checked').length === 1")
        bar = page.locator(".compare-bar")
        assert bar.is_visible()
        assert page.evaluate("document.documentElement.scrollWidth") <= PHONE  # no sideways scroll
        buttons = bar.locator("button")
        assert buttons.count() == 4  # Compare, Hide, Pin, Same journey (#2145)
        for i in range(4):
            box = buttons.nth(i).bounding_box()
            assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= PHONE
            covered = page.evaluate(
                """([x, y]) => { const el = document.elementFromPoint(x, y); return !!el && !!el.closest('.compare-bar'); }""",
                [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
            assert covered, f"button {i} is covered"
        assert dialogs == []
        context.close()
        browser.close()
