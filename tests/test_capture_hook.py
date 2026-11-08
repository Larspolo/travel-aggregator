"""The JavaScript hook of the `capture` skill in the browser: it records the responses of the requests that the page
itself sends (fetch and XMLHttpRequest), only for the matching URLs, and saves them as one HAR download that the
scrub accepts. Playwright serves all URLs from the test, so no request goes to a travel site (P1)."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import capture  # noqa: E402

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json").read_text("utf-8"))


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page(accept_downloads=True)

        def serve(route):
            url = route.request.url
            if "/web/api/angebote/" in url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(FIXTURE["response"]))
            elif "/web/api/" in url:
                route.fulfill(status=200, content_type="application/json", body='{"orte": []}')
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>test page</body></html>")

        pg.route("**/*", serve)
        pg.goto("https://travel.example/buchung/fahrplan/suche")
        yield pg
        browser.close()


def page_requests(pg):
    """The requests that the page app sends itself after a click (here: one fetch and one XHR, and one other)."""
    pg.evaluate("""b => Promise.all([
      fetch('/web/api/angebote/fahrplan', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: b})
        .then(r => r.json()),
      new Promise(ok => { const x = new XMLHttpRequest(); x.open('POST', '/web/api/angebote/tagesbestpreis');
        x.setRequestHeader('Content-Type', 'application/json'); x.onload = () => ok(x.status); x.send(b); }),
      fetch('/web/api/reiseloesung/orte?suchbegriff=K').then(r => r.json()),
    ])""", json.dumps(FIXTURE["request"]))


def test_hook_records_the_page_responses_and_saves_a_har(page, tmp_path):
    state = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert state == {"installed": True, "again": False, "auto": None, "fetch": True, "xhr": True, "response": True}
    page_requests(page)
    page.wait_for_function("window.__taCap.entries.length === 2")
    listed = json.loads(page.evaluate("window.__taCap.list()"))
    assert sorted(r["url"].rsplit("/", 1)[1] for r in listed) == ["fahrplan", "tagesbestpreis"]
    assert all(r["status"] == 200 and r["method"] == "POST" for r in listed)

    again = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert again["again"] is True and again["entries"] == 2

    with page.expect_download() as info:
        saved = json.loads(page.evaluate("window.__taCap.save('bahn.de 169')"))
    assert saved["saved"] == "bahn.de-169.har" and saved["entries"] == 2
    raw = tmp_path / info.value.suggested_filename
    info.value.save_as(raw)

    har, _ = capture.scrub([raw], identity=False)
    assert capture.problems(har, identity=False) == []
    fahrplan = next(e for e in har["log"]["entries"] if e["request"]["url"].endswith("/fahrplan"))
    assert json.loads(fahrplan["response"]["content"]["text"]) == FIXTURE["response"]
    assert json.loads(fahrplan["request"]["postData"]["text"]) == FIXTURE["request"]
    assert fahrplan["request"]["headers"] == [{"name": "content-type", "value": "application/json"}]
