"""The ÖBB userscript in the browser (#952): it sends the search and fare responses of the page as raw captures and no
other response. Playwright serves all URLs from the test, so the userscript sends no request to oebbtickets.at (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
OEBB = ROOT / "userscripts" / "oebb.user.js"
FIXTURES = ROOT / "tests" / "fixtures" / "oebbtickets.at"
SEARCH = json.loads((FIXTURES / "search-amsterdam-wien.json").read_text("utf-8"))
FARES = json.loads((FIXTURES / "fares-amsterdam-wien-nightjet.json").read_text("utf-8"))
SITE = "https://shop.oebbtickets.at"
SEARCH_PATH = "/api/hafas/v4/timetable"
FARES_PATH = "/api/offer/v6/offers"
PAGE_URL = f"{SITE}/en/ticket"
SEARCH_BODY = {"from": "Amsterdam Centraal", "to": "Wien Hbf", "date": "2026-12-01"}
FARES_BODY = {"connectionId": SEARCH["connections"][0]["id"]}
CONNECTIONS = len(SEARCH["connections"])
OFFERS = sum(len(c["offers"]) for s in FARES["offerSections"] for c in s["travelClasses"])
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Amsterdam'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""
PAGE = "<html><body><p>shop.oebbtickets.at test page</p></body></html>"
CORS = {"Access-Control-Allow-Origin": "*"}
RESPONSES = {SEARCH_PATH: SEARCH, FARES_PATH: FARES}


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        requests = []

        def serve(route):
            url = route.request.url
            requests.append(url)
            path = url.split("?")[0][len(SITE):] if url.startswith(SITE) else None
            if path in RESPONSES:
                route.fulfill(status=200, content_type="application/json", headers=CORS,
                              body=json.dumps(RESPONSES[path]))
            elif url.startswith(SITE):
                route.fulfill(status=200, content_type="application/json", headers=CORS, body="{}")
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + OEBB.read_text())
        pg.goto(PAGE_URL)
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def post(pg, path, body):
    pg.evaluate("""([u, b]) => fetch(u, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(b)}).then(r => r.json())""", [SITE + path, body])


def test_search_response_is_sent_as_raw_capture(page):
    post(page, SEARCH_PATH, SEARCH_BODY)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {CONNECTIONS} offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("oebbtickets.at", 5, "1.0.0")
    assert b["raw"]["url"] == SITE + SEARCH_PATH
    assert b["raw"]["method"] == "POST"
    assert b["raw"]["request"] == SEARCH_BODY
    assert b["raw"]["response"] == SEARCH
    assert set(page.requests) <= {PAGE_URL, SITE + SEARCH_PATH}


def test_fares_response_is_sent_as_raw_capture(page):
    post(page, FARES_PATH, FARES_BODY)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {OFFERS} offers → sent ✓"
    b = page.evaluate("window.__ingest")[0]["body"]
    assert b["raw"]["url"] == SITE + FARES_PATH
    assert b["raw"]["request"] == FARES_BODY
    assert b["raw"]["response"] == FARES


def test_other_responses_are_not_sent(page):
    page.evaluate("""() => Promise.all([
      fetch('https://shop.oebbtickets.at/api/other').then(r => r.text()),
      fetch('https://shop.oebbtickets.at/api/offer/v1/prices', {method: 'POST', body: '{}'}).then(r => r.text()),
    ])""")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert status(page) != f"Captured {CONNECTIONS} offers → sent ✓"
