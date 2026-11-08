"""The SNCF Connect userscript in the browser (#983): it sends a search response of the page as a raw capture, with only
`schedule` and `mainJourney` of the request body, and no other response. Playwright serves all URLs from the test, so
the userscript sends no request to sncf-connect.com (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
SNCF = ROOT / "userscripts" / "sncf.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "sncf-connect.com" / "search-paris-lyon.json")
                     .read_text("utf-8"))
SEARCH_URL = FIXTURE["url"]
SEARCH_HOST = "https://www.sncf-connect.com"
SEARCH_PATH = "/bff/api/v1/itineraries"
PAGE_URL = "https://www.sncf-connect.com/app/home/shop/results/outward"
# The page sends more than the search: a session id in the body must not reach the server (P5).
PAGE_BODY = dict(FIXTURE["request"], sessionId="secret-session-id")
BOOKABLE = sum(1 for p in FIXTURE["response"]["longDistance"]["proposals"]["proposals"]
               if p["status"]["isBookable"])
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Paris'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""
PAGE = "<html><body><p>sncf-connect.com test page</p></body></html>"
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
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + SNCF.read_text())
        pg.goto(PAGE_URL)
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def search(pg, kind):
    body = json.dumps(PAGE_BODY)
    if kind == "fetch":
        pg.evaluate("""([u, b]) => fetch(u, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: b}).then(r => r.json())""", [SEARCH_URL, body])
    else:
        pg.evaluate("""([u, b]) => new Promise(ok => { const x = new XMLHttpRequest();
          x.open('POST', u); x.setRequestHeader('Content-Type', 'application/json');
          x.onload = () => ok(x.status); x.send(b); })""", [SEARCH_URL, body])


@pytest.mark.parametrize("kind", ["fetch", "xhr"])
def test_search_response_is_sent_as_raw_capture(page, kind):
    search(page, kind)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {BOOKABLE} offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("sncf-connect.com", 5, "1.0.0")
    assert b["raw"]["url"] == SEARCH_URL
    assert b["raw"]["method"] == "POST"
    assert b["raw"]["request"] == {"schedule": FIXTURE["request"]["schedule"],
                                   "mainJourney": FIXTURE["request"]["mainJourney"]}
    assert b["raw"]["response"] == FIXTURE["response"]
    # The page made the search itself; the userscript sent no other request to sncf-connect.com.
    assert set(page.requests) <= {PAGE_URL, SEARCH_URL}


def test_other_responses_are_not_sent(page):
    page.evaluate("""() => Promise.all([
      fetch('https://www.sncf-connect.com/bff/api/v1/other', {method: 'POST', body: '{}'}).then(r => r.text()),
      fetch('https://www.sncf-connect.com/app/other').then(r => r.text()),
      new Promise(ok => { const x = new XMLHttpRequest(); x.open('POST', 'https://www.sncf-connect.com/bff/api/v1/other');
        x.onload = ok; x.send('{}'); }),
    ])""")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert status(page) != f"Captured {BOOKABLE} offers → sent ✓"
