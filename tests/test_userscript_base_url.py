"""bahn.de has `<base href="/web/">` and requests the relative URL `api/angebote/fahrplan`. core.js must resolve a
request URL against the base of the document, not against `location.href`, else the bahn.de userscript drops the
search (found in the owner check of #528 on 2026-11-07: status "ready", no capture on the server). Playwright serves
all URLs from the test, so no request goes to bahn.de (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
BAHN = ROOT / "userscripts" / "bahn.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json").read_text("utf-8"))
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Köln'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 201}), 0);
};
"""
PAGE = '<html><head><base href="/web/"></head><body><p>bahn.de test page</p></body></html>'


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if route.request.url.endswith("/web/api/angebote/fahrplan"):
                # bahn.de answers the search with status 201 (seen on 2026-11-07).
                route.fulfill(status=201, content_type="application/json", body=json.dumps(FIXTURE["response"]))
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + BAHN.read_text())
        pg.goto("https://www.bahn.de/buchung/fahrplan/suche")
        yield pg
        browser.close()


@pytest.mark.parametrize("kind", ["fetch", "xhr"])
def test_a_relative_request_url_is_resolved_against_the_base_of_the_page(page, kind):
    assert page.evaluate("document.baseURI") == "https://www.bahn.de/web/"
    body = json.dumps(FIXTURE["request"])
    if kind == "fetch":
        page.evaluate("b => fetch('api/angebote/fahrplan', {method: 'POST', body: b}).then(r => r.status)", body)
    else:
        page.evaluate("""b => new Promise(ok => { const x = new XMLHttpRequest();
          x.open('POST', 'api/angebote/fahrplan'); x.onload = () => ok(x.status); x.send(b); })""", body)
    page.wait_for_function("window.__ingest.length === 1")
    sent = page.evaluate("window.__ingest")[0]
    assert sent["body"]["source"] == "bahn.de"
    assert sent["body"]["raw"]["response"] == FIXTURE["response"]
    assert sent["body"]["raw"]["request"] == FIXTURE["request"]
