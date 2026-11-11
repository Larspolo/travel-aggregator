"""The panel tells why it missed a capture (#1072): the resource timing shows an accepted request of the page that
the hook did not see. Playwright serves all URLs from routes, so no request goes to a travel site (P1)."""

import os
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {server: "https://ta.example", token: "t"};
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_xmlhttpRequest = (d) => setTimeout(() => d.onload({status: 200, responseText: "[]"}), 0);
"""
WATCH = "TACore.watch(TACore.urlTest((u) => u.pathname === '/gateway'), () => {});"
ROOT = "document.getElementById('ta-core-panel').shadowRoot"


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.route("https://site.test/**", lambda r: r.fulfill(body="<html><body></body></html>" if
                 r.request.url.endswith("/") else '{"data": {}}', content_type="text/html"))
        pg.goto("https://site.test/")
        yield pg
        browser.close()


def _xhr(pg):
    pg.evaluate("""() => new Promise((ok) => { const x = new XMLHttpRequest(); x.open('POST', '/gateway');
        x.onload = ok; x.send('{}'); })""")


def _load_core(pg):
    pg.add_script_tag(content=STUBS)
    pg.add_script_tag(content=CORE.read_text())
    pg.evaluate(WATCH)


@pytest.mark.slow
def test_request_before_the_core_is_named(page):
    _xhr(page)
    _load_core(page)
    text = page.evaluate("TACore.diagnose()")
    assert text.startswith("Missed 1 search responses: they came before the script started")
    assert page.evaluate(f"{ROOT}.querySelector('.panel').className") == "panel warn"


@pytest.mark.slow
def test_page_wrapper_before_the_core_is_named(page):
    page.evaluate("""() => { const s = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function () { return s.apply(this, arguments); };
        window.__send = XMLHttpRequest.prototype.send; }""")
    _load_core(page)
    # The page calls the send that it saved before the core: the hook does not see it.
    page.evaluate("""() => new Promise((ok) => { const x = new XMLHttpRequest(); x.open('POST', '/gateway');
        x.onload = ok; window.__send.call(x, '{}'); })""")
    assert "the page wrapped XMLHttpRequest first" in page.evaluate("TACore.diagnose()")


@pytest.mark.slow
def test_seen_request_gives_no_diagnosis(page):
    _load_core(page)
    _xhr(page)
    assert page.evaluate("TACore.diagnose()") is None
