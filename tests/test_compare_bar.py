"""The trip page shows a "Compare N selected" bar when rows are ticked (#664), with CSS only."""

import os

import pytest
from tests.test_mobile_controls import _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

SHOTS = os.environ.get("COMPARE_BAR_SHOTS")


def _tick(page, n):
    boxes = page.locator("#table input[name=it]")
    for i in range(n):
        boxes.nth(i).check()


@pytest.mark.parametrize("width", [1280, 390])
def test_two_ticked_rows_show_the_bar_and_open_the_compare_page(live, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, tid = live
    with sync_playwright() as p:
        browser = _launch(p)
        for scheme in ("light", "dark"):
            page = browser.new_page(viewport={"width": width, "height": 800}, color_scheme=scheme)
            page.goto(f"{base}/trips/{tid}")
            assert page.locator("header button[form=compare], .page-header button[form=compare]").count() == 0
            bar = page.locator(".compare-bar")
            assert not bar.is_visible()
            # a slider change swaps the compare form out of band; the bar must still work after it
            page.evaluate("""() => { const r = document.querySelector('form.weights input[name=hour_markup]');
                r.value = '37'; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
            page.wait_for_function("document.querySelector('#compare input[name=hour_markup][value=\"37\"]') !== null")
            _tick(page, 2)
            assert bar.is_visible()
            text = page.evaluate("getComputedStyle(document.querySelector('.compare-count'), '::before').content")
            # the browser does not resolve counter() in getComputedStyle: check the rule and the ticked boxes
            assert text == '"Compare " counter(picked) " selected"'
            assert page.locator("#table input[name=it]:checked").count() == 2
            box = bar.bounding_box()
            assert box["y"] + box["height"] <= 800  # sticky: near the rows, in the viewport
            if SHOTS:
                page.screenshot(path=f"{SHOTS}/bar-{width}-{scheme}.png")
            ids = page.eval_on_selector_all("#table input[name=it]:checked", "els => els.map(e => e.value)")
            bar.locator("button:not([formaction])").click()  # the Compare button; Hide and Pin have a formaction (#1897)
            page.wait_for_url(f"**/trips/{tid}/compare?*")
            assert sorted(ids) == sorted(v for k, v in [q.split("=") for q in page.url.split("?")[1].split("&")]
                                         if k == "it")
            assert "Select 2 to 4" not in page.content()
            page.close()
        browser.close()
