"""The menus and the trip controls work with Tab, Enter and Escape (#820)."""

import os

import pytest

from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow


def open_page(p, url, width):
    exe = "/opt/pw-browsers/chromium"
    browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": 844})
    page.goto(url)
    page.wait_for_selector("#rows > tr:not(.detail)")
    return browser, page


def tab_to(page, selector, limit=80):
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate("s => document.activeElement.matches(s)", selector):
            return
    raise AssertionError(f"Tab does not reach {selector}")


@pytest.mark.parametrize(("width", "menu"), [(390, "details.menu"), (1280, "details.more")])
def test_tab_enter_and_escape_on_a_menu(live, width, menu):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = open_page(p, live, width)
        tab_to(page, f"{menu} > summary")
        page.keyboard.press("Enter")
        page.wait_for_function(f"document.querySelector('{menu}').open")
        page.keyboard.press("Escape")
        page.wait_for_function(f"!document.querySelector('{menu}').open")
        focused = page.evaluate(f"document.activeElement === document.querySelector('{menu} > summary')")
        browser.close()
    assert focused, "the focus is not on the summary of the menu after Escape"


def test_arrow_right_on_a_slider_reranks(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = open_page(p, live, 1280)
        slider = page.locator("input[type=range][name=hour_markup]")
        before = slider.input_value()
        slider.focus()
        with page.expect_response(lambda r: "hour_markup=" in r.url):
            page.keyboard.press("ArrowRight")
        after = slider.input_value()
        browser.close()
    assert int(after) == int(before) + 1


def test_enter_opens_the_row_detail(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = open_page(p, live, 1280)
        summary = page.locator("tr.detail details > summary").first
        summary.focus()
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('tr.detail details').open")
        browser.close()


def test_each_tab_stop_of_the_trip_page_has_a_focus_mark(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = open_page(p, live, 1280)
        missing, seen = [], set()
        for _ in range(150):
            page.keyboard.press("Tab")
            info = page.evaluate(
                """() => { const e = document.activeElement; if (!e || e === document.body) return null;
                const s = getComputedStyle(e);
                const mark = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
                return {key: e.outerHTML.slice(0, 120), mark}; }"""
            )
            if info is None or info["key"] in seen:
                break
            seen.add(info["key"])
            if not info["mark"]:
                missing.append(info["key"])
        browser.close()
    assert len(seen) > 5
    assert not missing, f"no focus mark: {missing}"
