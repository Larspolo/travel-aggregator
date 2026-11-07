"""The capture hook records the request body also when the page sends a Request object, as Skyscanner does (#463).
Playwright serves all URLs from the test, so no request goes to a travel site (P1)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import capture  # noqa: E402

pytestmark = pytest.mark.slow
BODY = json.dumps({"adults": 1, "cabinClass": "ECONOMY", "legs": [{"origin": "AMS", "destination": "LIS"}]})


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if "/g/radar/" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body='{"context": {"status": "complete"}}')
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>test page</body></html>")

        pg.route("**/*", serve)
        pg.goto("https://flights.example/transport/vluchten/ams/lis/261201/")
        yield pg
        browser.close()


def entry(page):
    page.wait_for_function("window.__taCap.entries.length === 1")
    return page.evaluate("window.__taCap.entries[0]")


def test_hook_records_the_body_and_type_of_a_request_object(page):
    page.evaluate(capture.hook(r"/g/radar/"))
    status = page.evaluate("""async b => {
      const req = new Request('/g/radar/api/v2/web-unified-search/',
        {method: 'POST', body: b, headers: {'content-type': 'application/json'}});
      return (await fetch(req)).status;
    }""", BODY)
    assert status == 200
    e = entry(page)
    assert e["request"]["method"] == "POST"
    assert e["request"]["postData"] == {"mimeType": "application/json", "text": BODY}
    assert e["request"]["headers"] == [{"name": "content-type", "value": "application/json"}]


def test_hook_records_a_blob_body(page):
    page.evaluate(capture.hook(r"/g/radar/"))
    page.evaluate("""async b => (await fetch('/g/radar/x', {method: 'POST', body: new Blob([b])})).text()""", BODY)
    assert entry(page)["request"]["postData"]["text"] == BODY


def test_hook_records_no_body_for_a_get_request_object(page):
    page.evaluate(capture.hook(r"/g/radar/"))
    page.evaluate("async () => (await fetch(new Request('/g/radar/poll/token'))).text()")
    assert "postData" not in entry(page)["request"]
