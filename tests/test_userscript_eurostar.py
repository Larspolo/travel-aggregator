"""The Eurostar userscript in the browser (#1019): it sends a NewBookingSearch response of the page as a raw capture,
without the GraphQL query text of the request, and no other operation. Playwright serves all URLs from the test, so the
userscript sends no request to eurostar.com (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
EUROSTAR = ROOT / "userscripts" / "eurostar.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "eurostar.com" / "search-amsterdam-london.json")
                     .read_text("utf-8"))
SEARCH_URL = FIXTURE["url"]
SEARCH_HOST = "https://site-api.eurostar.com"
SEARCH_PATH = "/gateway"
PAGE_URL = "https://www.eurostar.com/search/uk-en?adult=1&origin=8400058&destination=7015400&outbound=2026-12-01"
JOURNEYS = len(FIXTURE["response"]["data"]["journeySearch"]["outbound"]["journeys"])
REQUEST_BODY = dict(FIXTURE["request"]["body"],
                    query="query NewBookingSearch($origin: String!) { journeySearch { outbound { journeys { timing } } } }")
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
PAGE = "<html><body><p>eurostar.com test page</p></body></html>"
CORS = {"Access-Control-Allow-Origin": "*"}


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
            if url.startswith(SEARCH_HOST) and url.split("?")[0].endswith(SEARCH_PATH):
                route.fulfill(status=200, content_type="application/json", headers=CORS,
                              body=json.dumps(FIXTURE["response"]))
            elif url.startswith(SEARCH_HOST):
                route.fulfill(status=200, content_type="application/json", headers=CORS, body="{}")
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + EUROSTAR.read_text())
        pg.goto(PAGE_URL)
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def post(pg, body, kind):
    text = json.dumps(body)
    if kind == "fetch":
        js = """([u, b]) => fetch(u, {method: 'POST', headers: {'content-type': 'application/json'}, body: b})
          .then(r => r.json())"""
    else:
        js = """([u, b]) => new Promise(ok => { const x = new XMLHttpRequest();
          x.open('POST', u); x.setRequestHeader('content-type', 'application/json');
          x.onload = () => ok(x.status); x.send(b); })"""
    pg.evaluate(js, [SEARCH_URL, text])


@pytest.mark.parametrize("kind", ["fetch", "xhr"])
def test_search_response_is_sent_as_raw_capture(page, kind):
    post(page, REQUEST_BODY, kind)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {JOURNEYS} offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("eurostar.com", 5, "1.0.0")
    raw = b["raw"]
    assert raw["url"] == SEARCH_URL
    assert raw["method"] == "POST"
    assert raw["response"] == FIXTURE["response"]
    # Only the operation and its variables are sent: the GraphQL query text is not.
    assert raw["request"]["body"] == {"operationName": "NewBookingSearch",
                                      "variables": REQUEST_BODY["variables"]}
    assert "query" not in json.dumps(raw["request"])
    # The page made the search itself; the userscript sent no other request to eurostar.com.
    assert set(page.requests) <= {PAGE_URL, SEARCH_URL}


def test_other_operations_are_not_sent(page):
    other = {"operationName": "FareConditions", "variables": {}, "query": "query FareConditions { x }"}
    page.evaluate("""([u, b]) => fetch(u, {method: 'POST', headers: {'content-type': 'application/json'},
      body: b}).then(r => r.text())""", [SEARCH_URL, json.dumps(other)])
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert status(page) != f"Captured {JOURNEYS} offers → sent ✓"
