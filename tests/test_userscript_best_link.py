"""The panel links the best offer to its row on the trip page (#2367). Playwright stubs GM_xmlhttpRequest, so no
request goes to a server or a travel site (P1)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = { server: 'https://travel.example', token: 'token', trip: 12, autosend: true };
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_info = () => ({ script: {} });
window.__body = '{}';
window.GM_xmlhttpRequest = (o) => {
  setTimeout(() => o.onload({ status: 200, responseText: window.__body }), 0);
};
"""
PAGE = "<html><head></head><body></body></html>"


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(PAGE)
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
        yield pg
        browser.close()


def send_with_body(pg, body):
    pg.evaluate("(body) => { window.__body = body; }", body)
    pg.evaluate("TACore.send({ source: 'test', offers: [{ price: '1.00' }] })")
    pg.wait_for_function("() => document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.panel').textContent.includes('sent')")


def status(pg):
    return pg.evaluate("""() => { const b = document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel');
        const a = b.querySelector('.best-link');
        return {text: b.textContent, href: a ? a.getAttribute('href') : null,
                target: a ? a.getAttribute('target') : null, linkText: a ? a.textContent : null}; }""")


def test_the_best_is_a_link_to_its_itinerary_row(page):
    send_with_body(page, '{"trip_id": 12, "accepted": 1, "best": {"total": "104.50", "new": true, "itinerary_id": 345}}')
    assert status(page) == {"text": "Captured 1 offers → sent ✓ · Best of trip: €104.50 (new)",
                            "href": "https://travel.example/trips/12#it-345", "target": "_blank",
                            "linkText": "Best of trip: €104.50 (new)"}


def test_a_best_without_itinerary_id_is_plain_text(page):
    send_with_body(page, '{"trip_id": 12, "accepted": 1, "best": {"total": "104.50", "new": false}}')
    assert status(page) == {"text": "Captured 1 offers → sent ✓ · Best of trip: €104.50",
                            "href": None, "target": None, "linkText": None}


def test_no_best_shows_no_link(page):
    send_with_body(page, '{"trip_id": 12, "accepted": 1, "best": null}')
    assert status(page)["href"] is None


def test_a_click_on_the_link_does_not_fold_the_panel(page):
    send_with_body(page, '{"trip_id": 12, "accepted": 1, "best": {"total": "104.50", "new": true, "itinerary_id": 345}}')
    page.evaluate("""() => { const a = document.getElementById('ta-core-panel').shadowRoot.querySelector('.best-link');
        a.addEventListener('click', (e) => e.preventDefault(), { once: true }); a.click(); }""")
    folded = page.evaluate("() => document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".parentElement.classList.contains('collapsed')")
    assert folded is False
