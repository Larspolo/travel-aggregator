"""The Trainline userscript in the browser (#978): it sends a journey search response of the page as a raw capture,
without the date of birth of the request, and no other response. Playwright serves all URLs from the test, so the
userscript sends no request to thetrainline.com (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
TRAINLINE = ROOT / "userscripts" / "trainline.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "thetrainline.com" / "search-london-edinburgh.json")
                     .read_text("utf-8"))
SEARCH_URL = FIXTURE["url"]
SEARCH_HOST = "https://www.thetrainline.com"
SEARCH_PATH = "/api/journey-search/"
PAGE_URL = "https://www.thetrainline.com/"
JOURNEYS = len(FIXTURE["response"]["data"]["journeySearch"]["journeys"])
REQUEST_BODY = FIXTURE["request"]["body"]
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'London'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""
PAGE = "<html><body><p>thetrainline.com test page</p></body></html>"
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
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + TRAINLINE.read_text())
        pg.goto(PAGE_URL)
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def search(pg, kind):
    body = json.dumps(REQUEST_BODY)
    if kind == "fetch":
        js = """([u, b]) => fetch(u, {method: 'POST', headers: {'content-type': 'application/json'}, body: b})
          .then(r => r.json())"""
    else:
        js = """([u, b]) => new Promise(ok => { const x = new XMLHttpRequest();
          x.open('POST', u); x.setRequestHeader('content-type', 'application/json');
          x.onload = () => ok(x.status); x.send(b); })"""
    pg.evaluate(js, [SEARCH_URL, body])


@pytest.mark.parametrize("kind", ["fetch", "xhr"])
def test_search_response_is_sent_as_raw_capture(page, kind):
    search(page, kind)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {JOURNEYS} offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("thetrainline.com", 5, "1.0.0")
    raw = b["raw"]
    assert raw["url"] == SEARCH_URL
    assert raw["method"] == "POST"
    assert raw["response"] == FIXTURE["response"]
    # The date of birth is not sent: the request has the passengers without it.
    assert raw["request"]["body"]["passengers"] == [{k: v for k, v in p.items() if k != "dateOfBirth"}
                                                    for p in REQUEST_BODY["passengers"]]
    assert "dateOfBirth" not in json.dumps(raw["request"])
    # The page made the search itself; the userscript sent no other request to thetrainline.com.
    assert set(page.requests) <= {PAGE_URL, SEARCH_URL}


def test_other_responses_are_not_sent(page):
    page.evaluate("""() => Promise.all([
      fetch('https://www.thetrainline.com/api/other').then(r => r.text()),
      fetch('https://www.thetrainline.com/api/journey-search-history').then(r => r.text()),
    ])""")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert status(page) != f"Captured {JOURNEYS} offers → sent ✓"
