"""The capture hook records the responses that the page reads, also when the page keeps its own fetch reference or the
hook cannot replace window.fetch (#399). Playwright serves all URLs from the test, so no request goes to a travel site
(P1)."""
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
FETCH_JS = """async b => {
  const r = await FETCH('/web/api/angebote/fahrplan', {method: 'POST', body: b});
  return await r.text();
}"""


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if "/web/api/angebote/" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(FIXTURE["response"]))
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>test page</body></html>")

        pg.route("**/*", serve)
        pg.goto("https://travel.example/buchung/fahrplan/suche")
        yield pg
        browser.close()


def test_hook_records_a_fetch_that_the_page_kept_from_before_the_hook(page):
    page.evaluate("window.__appFetch = window.fetch")
    state = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert state["response"] is True
    text = page.evaluate(FETCH_JS.replace("FETCH", "window.__appFetch"), json.dumps(FIXTURE["request"]))
    page.wait_for_function("window.__taCap.entries.length === 1")
    entry = page.evaluate("window.__taCap.entries[0]")
    assert entry["request"]["url"].endswith("/web/api/angebote/fahrplan")
    assert entry["request"]["method"] == ""
    assert "postData" not in entry["request"]
    assert entry["response"]["status"] == 200
    assert entry["response"]["content"]["text"] == text
    assert json.loads(text) == FIXTURE["response"]


def test_hook_records_a_page_response_once_when_window_fetch_cannot_be_replaced(page):
    page.evaluate("Object.defineProperty(window, 'fetch', {value: window.fetch, writable: false})")
    state = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert state == {"installed": True, "again": False, "fetch": False, "xhr": True, "response": True}
    text = page.evaluate("async () => (await (await fetch('/web/api/angebote/fahrplan', {method: 'POST', body: '{}'}))"
                         ".text())")
    page.wait_for_function("window.__taCap.entries.length === 1")
    page.evaluate("async () => (await fetch('/web/api/reiseloesung/orte')).status")
    assert page.evaluate("window.__taCap.entries.length") == 1
    assert page.evaluate("window.__taCap.entries[0].response.content.text") == text


def test_hook_records_a_fetch_once_when_the_fetch_wrapper_records_it(page):
    state = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert state["fetch"] is True
    page.evaluate("""async b => (await (await fetch('/web/api/angebote/fahrplan', {method: 'POST', body: b})).json())""",
                  json.dumps(FIXTURE["request"]))
    page.wait_for_function("window.__taCap.entries.length === 1")
    page.evaluate("async () => (await fetch('/web/api/angebote/fahrplan', {method: 'POST', body: '{}'})).text()")
    page.wait_for_function("window.__taCap.entries.length === 2")
    entries = page.evaluate("window.__taCap.entries")
    assert [e["request"]["method"] for e in entries] == ["POST", "POST"]
    assert all(e["response"]["content"]["text"] for e in entries)
