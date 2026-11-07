"""The capture hook records an XHR response that the page reads only with the `responseText` getter, and it records
each response one time (#169). Playwright serves all URLs from the test, so no request goes to a travel site (P1)."""
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
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>test page</body></html>")

        pg.route("**/*", serve)
        pg.goto("https://travel.example/buchung/fahrplan/suche")
        yield pg
        browser.close()


def test_getter_records_an_xhr_that_only_the_getter_sees_once(page):
    # The request is opened before the hook exists, so the open/send wrappers do not see it. The page reads the
    # response only through the responseText getter, and loadend fires after that read.
    page.evaluate("""b => {
      const x = new XMLHttpRequest();
      x.open('POST', '/web/api/angebote/fahrplan');
      x.setRequestHeader('Content-Type', 'application/json');
      window.__x = x;
      window.__body = b;
    }""", json.dumps(FIXTURE["request"]))
    state = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert state["xhr"] is True and state["response"] is True
    page.evaluate("""() => {
      const x = window.__x;
      window.__read = null;
      window.__loadend = false;
      x.addEventListener('loadend', () => { window.__loadend = true; });
      x.onreadystatechange = () => { if (x.readyState === 4) window.__read = x.responseText.length; };
      x.send(window.__body);
    }""")
    page.wait_for_function("window.__loadend === true && window.__read !== null")
    listed = json.loads(page.evaluate("window.__taCap.list()"))
    assert len(listed) == 1
    assert listed[0]["url"].endswith("/web/api/angebote/fahrplan")
    assert listed[0]["status"] == 200
    assert listed[0]["size"] == page.evaluate("window.__read")


def test_open_send_request_read_by_the_getter_is_recorded_once(page):
    # The open/send wrappers see this request and the page reads responseText twice: one entry only.
    state = json.loads(page.evaluate(capture.hook(r"/web/api/angebote/")))
    assert state["xhr"] is True
    page.evaluate("""b => new Promise(ok => {
      const x = new XMLHttpRequest();
      x.open('POST', '/web/api/angebote/tagesbestpreis');
      x.setRequestHeader('Content-Type', 'application/json');
      x.onload = () => { x.responseText; x.responseText; ok(); };
      x.send(b);
    })""", json.dumps(FIXTURE["request"]))
    page.wait_for_function("window.__taCap.entries.length >= 1")
    page.wait_for_timeout(200)
    listed = json.loads(page.evaluate("window.__taCap.list()"))
    assert [r["url"].rsplit("/", 1)[1] for r in listed] == ["tagesbestpreis"]
