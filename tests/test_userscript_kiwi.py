"""The kiwi.com userscript in the browser (#332): it sends a SearchOneWayItinerariesQuery response of the page as a raw
capture (with the request currency) and no other response. Playwright serves all URLs from the test, so no request
goes to kiwi.com or skypicker.com from the userscript (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
KIWI = ROOT / "userscripts" / "kiwi.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "kiwi.com" / "search-amsterdam-zurich.json").read_text("utf-8"))
API = "https://api.skypicker.com/umbrella/v2/graphql"
SEARCH_QUERY = "?featureName=SearchOneWayItinerariesQuery"
REQUEST = {"query": "query SearchOneWayItinerariesQuery { onewayItineraries }",
           "variables": {"options": {"currency": FIXTURE["currency"]}}}
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
PAGE = "<html><body><p>kiwi.com test page</p></body></html>"


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
            if url.startswith(API) and "featureName=SearchOneWayItinerariesQuery" in url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(FIXTURE["response"]))
            elif url.startswith(API):
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"data": {}}))
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + KIWI.read_text())
        pg.goto("https://www.kiwi.com/en/search")
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def search(pg, kind):
    url = API + SEARCH_QUERY
    body = json.dumps(REQUEST)
    if kind == "fetch":
        js = "([u, b]) => fetch(u, {method: 'POST', body: b}).then(r => r.json())"
    else:
        js = """([u, b]) => new Promise(ok => { const x = new XMLHttpRequest();
          x.open('POST', u); x.onload = () => ok(x.status); x.send(b); })"""
    pg.evaluate(js, [url, body])


@pytest.mark.parametrize("kind", ["fetch", "xhr"])
def test_search_response_is_sent_as_raw_capture(page, kind):
    search(page, kind)
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == "Captured 3 offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("kiwi.com", 5, "1.0.0")
    assert b["raw"] == {"currency": "gbp", "response": FIXTURE["response"]}
    assert all(u.startswith("https://www.kiwi.com/") or u.startswith(API) for u in page.requests)


def test_other_responses_are_not_sent(page):
    page.evaluate("""() => Promise.all([
      fetch('https://api.skypicker.com/umbrella/v2/graphql?featureName=OtherQuery', {method: 'POST', body: '{}'})
        .then(r => r.json()),
      fetch('/en/stations').then(r => r.text()),
      new Promise(ok => { const x = new XMLHttpRequest(); x.open('GET', '/en/stations');
        x.onload = ok; x.send(); }),
    ])""")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert status(page) != "Captured 3 offers → sent ✓"
