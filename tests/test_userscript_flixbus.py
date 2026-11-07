"""The Flixbus userscript in the browser (#251): it sends a search response of the page as a raw capture and no other
response. Playwright serves all URLs from the test, so the userscript sends no request to flixbus.com (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
FLIXBUS = ROOT / "userscripts" / "flixbus.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "flixbus.com" / "search-amsterdam-berlin.json")
                     .read_text("utf-8"))
SEARCH_URL = FIXTURE["url"]
SEARCH_HOST = "https://global.api.flixbus.com"
SEARCH_PATH = "/search/service/v4/search"
PAGE_URL = "https://www.flixbus.com/en/search"
CONNECTIONS = sum(len(t["results"]) for t in FIXTURE["response"]["trips"])
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
PAGE = "<html><body><p>flixbus.com test page</p></body></html>"
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
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + FLIXBUS.read_text())
        pg.goto(PAGE_URL)
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def search(pg, kind):
    if kind == "fetch":
        js = "(u) => fetch(u).then(r => r.json())"
    else:
        js = """(u) => new Promise(ok => { const x = new XMLHttpRequest();
          x.open('GET', u); x.onload = () => ok(x.status); x.send(); })"""
    pg.evaluate(js, SEARCH_URL)


@pytest.mark.parametrize("kind", ["fetch", "xhr"])
def test_search_response_is_sent_as_raw_capture(page, kind):
    search(page, kind)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {CONNECTIONS} offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("flixbus.com", 5, "1.0.0")
    assert b["raw"]["url"] == SEARCH_URL
    assert b["raw"]["method"] == "GET"
    assert b["raw"]["request"] is None
    assert b["raw"]["response"] == FIXTURE["response"]
    # The page made the search itself; the userscript sent no other request to flixbus.com.
    assert set(page.requests) <= {PAGE_URL, SEARCH_URL}


def test_other_responses_are_not_sent(page):
    page.evaluate("""() => Promise.all([
      fetch('https://global.api.flixbus.com/search/service/v4/cities').then(r => r.text()),
      fetch('https://www.flixbus.com/api/other').then(r => r.text()),
      new Promise(ok => { const x = new XMLHttpRequest(); x.open('GET', 'https://global.api.flixbus.com/search/service/v4/cities');
        x.onload = ok; x.send(); }),
    ])""")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert status(page) != f"Captured {CONNECTIONS} offers → sent ✓"
