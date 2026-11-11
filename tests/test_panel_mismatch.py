"""The panel shows the trip warning of an ingest response (#557): the offers do not match the trip. Playwright stubs
GM_xmlhttpRequest, so no request goes to a server or a travel site (P1)."""

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


def test_a_warning_in_the_response_shows_the_warning_in_the_warn_style(page):
    send_with_body(page, '{"accepted": 1, "warning": "places"}')
    shown = panel(page)
    assert shown["text"] == WARNING
    assert shown["kind"] == "warn"


def test_no_warning_shows_sent_in_the_ok_style(page):
    send_with_body(page, '{"accepted": 1, "warning": null}')
    shown = panel(page)
    assert shown["text"] == "Captured 1 offers → sent ✓"
    assert shown["kind"] == "ok"


def test_a_response_that_is_not_json_shows_sent_in_the_ok_style(page):
    send_with_body(page, "not json")
    assert panel(page) == {"text": "Captured 1 offers → sent ✓", "kind": "ok"}
