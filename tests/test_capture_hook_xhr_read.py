"""The capture hook records an XHR response also when the page sends it with its own saved `open` and `send` (bahn.de,
#238), decodes a binary `responseType`, and saves the inline data of a page that puts its results into the HTML
(Google Flights, #238). Playwright serves all URLs from the test, so no request goes to a travel site (P1)."""
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
INLINE = "AF_initDataCallback({key: 'ds:1', hash: '9', data:[[\"KLM\",[[null,154],\"x\"]]], sideChannel: {}});"
PAGE = (f"<html><body><script>{INLINE}</script><script>AF_initDataCallback({{key: 'ds:0', data:[]}});</script>"
        "test page</body></html>")


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if "/web/api/angebote/" in route.request.url:
                route.fulfill(status=201, content_type="application/json", body=json.dumps(FIXTURE["response"]))
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.goto("https://travel.example/travel/flights/search?tfs=abc")
        yield pg
        browser.close()


SAVED_XHR = """b => new Promise(ok => {
  const x = new XMLHttpRequest();
  window.__open.call(x, 'POST', '/web/api/angebote/fahrplan');
  x.responseType = TYPE;
  x.onload = () => { const v = READ; ok(typeof v === 'string' ? v : 'binary'); };
  window.__send.call(x, b);
})"""


def send_with_saved_methods(pg, rtype="''", read="x.responseText"):
    return pg.evaluate(SAVED_XHR.replace("TYPE", rtype).replace("READ", read), json.dumps(FIXTURE["request"]))


def test_hook_records_an_xhr_that_the_page_sends_with_saved_open_and_send(page):
    page.evaluate("window.__open = XMLHttpRequest.prototype.open; window.__send = XMLHttpRequest.prototype.send; 0")
    json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    text = send_with_saved_methods(page)
    page.wait_for_function("window.__taCap.entries.length === 1")
    page.wait_for_timeout(200)
    entries = page.evaluate("window.__taCap.entries")
    assert len(entries) == 1
    assert entries[0]["request"]["url"].endswith("/web/api/angebote/fahrplan")
    assert entries[0]["response"]["status"] == 201
    assert entries[0]["response"]["content"]["text"] == text
    assert json.loads(text) == FIXTURE["response"]


def test_hook_records_an_xhr_once_with_its_request_when_the_page_reads_it_in_onload(page):
    json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    page.evaluate("window.__open = XMLHttpRequest.prototype.open; window.__send = XMLHttpRequest.prototype.send; 0")
    send_with_saved_methods(page)
    page.wait_for_function("window.__taCap.entries.length === 1")
    page.wait_for_timeout(200)
    entries = page.evaluate("window.__taCap.entries")
    assert len(entries) == 1
    assert entries[0]["request"]["method"] == "POST"
    assert json.loads(entries[0]["request"]["postData"]["text"]) == FIXTURE["request"]


def test_hook_decodes_an_xhr_with_an_arraybuffer_response(page):
    json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    page.evaluate("window.__open = XMLHttpRequest.prototype.open; window.__send = XMLHttpRequest.prototype.send; 0")
    assert send_with_saved_methods(page, "'arraybuffer'", "x.response") == "binary"
    page.wait_for_function("window.__taCap.entries.length === 1")
    text = page.evaluate("window.__taCap.entries[0].response.content.text")
    assert json.loads(text) == FIXTURE["response"]


def test_inline_adds_the_matching_inline_scripts_of_the_page_as_entries(page):
    json.loads(page.evaluate(capture.hook(r"google\.com|travel\.example/travel/flights/search")))
    state = json.loads(page.evaluate("window.__taCap.inline(\"key: 'ds:1'\")"))
    assert state == {"added": 1, "entries": 1}
    entry = page.evaluate("window.__taCap.entries[0]")
    assert entry["request"]["method"] == "GET"
    assert entry["request"]["url"] == "https://travel.example/travel/flights/search?tfs=abc"
    assert entry["response"]["content"]["text"] == INLINE
    assert entry["response"]["content"]["mimeType"] == "text/javascript"
    assert json.loads(page.evaluate("window.__taCap.inline(\"key: 'ds:1'\")")) == {"added": 0, "entries": 1}
