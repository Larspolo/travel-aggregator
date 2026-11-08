"""The panel shows the best offer of the trip after a sent capture (#881). Playwright stubs GM_xmlhttpRequest, so no
request goes to a server or a travel site (P1)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = { server: 'https://travel.example', token: 'token', trip: 1, autosend: true };
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_info = () => ({ script: {} });
window.__body = '{}';
window.GM_xmlhttpRequest = (o) => {
  setTimeout(() => o.onload({ status: 200, responseText: window.__body }), 0);
};
"""
PAGE = "<html><head></head><body></body></html>"
SENT = "Captured 1 offers → sent ✓"
WARNING = "Captured 1 offers → sent ✓, but these offers do not match the trip"


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


def panel(pg):
    return pg.evaluate("""() => { const b = document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel');
        return {text: b.textContent, kind: b.className.replace('panel ', '')}; }""")


def send_with_body(pg, body):
    pg.evaluate("(body) => { window.__body = body; }", body)
    pg.evaluate("TACore.send({ source: 'test', offers: [{ price: '1.00' }] })")
    pg.wait_for_function("() => document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.panel').textContent.includes('sent')")


def test_a_new_best_with_whole_euros_shows_the_best_without_decimals(page):
    send_with_body(page, '{"accepted": 1, "best": {"total": "182.00", "new": true}}')
    assert panel(page) == {"text": "Captured 1 offers → sent ✓ · Best of trip: €182 (new)", "kind": "ok"}


def test_a_best_with_cents_shows_two_decimals_and_no_new_mark(page):
    send_with_body(page, '{"accepted": 1, "best": {"total": "165.50", "new": false}}')
    assert panel(page) == {"text": "Captured 1 offers → sent ✓ · Best of trip: €165.50", "kind": "ok"}


def test_no_best_keeps_the_sent_text(page):
    send_with_body(page, '{"accepted": 1}')
    assert panel(page) == {"text": SENT, "kind": "ok"}


def test_a_null_best_keeps_the_sent_text(page):
    send_with_body(page, '{"accepted": 1, "best": null}')
    assert panel(page) == {"text": SENT, "kind": "ok"}


def test_a_warning_keeps_its_warn_style_with_the_best_after_it(page):
    send_with_body(page, '{"accepted": 1, "warning": "places", "best": {"total": "165.50", "new": false}}')
    assert panel(page) == {"text": WARNING + " · Best of trip: €165.50", "kind": "warn"}
