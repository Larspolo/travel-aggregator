"""The ÖBB userscript with relative request URLs (#1075): the results list at `/en/ticket/timetable` requests
`api/hafas/v4/timetable` and `api/offer/v1/prices` relative to `<base href="/">`. The capture must have the
connections with their prices, and a capture with 0 offers is not sent. Playwright serves all URLs (P1)."""

import json
import os

import pytest

from tests import test_userscript_oebb as base

pytestmark = pytest.mark.slow
PAGE_URL = f"{base.SITE}/en/ticket/timetable"
PAGE = '<html><head><base href="/"></head><body><p>timetable</p></body></html>'


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium"
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            url = route.request.url
            path = url.split("?")[0][len(base.SITE):] if url.startswith(base.SITE) else None
            if path in base.RESPONSES:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(base.RESPONSES[path]))
            elif url.startswith(base.SITE + "/api/"):
                route.fulfill(status=200, content_type="application/json", body="{}")
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(base.STUBS + base.CORE.read_text() + "\n" + base.OEBB.read_text())
        pg.goto(PAGE_URL)
        yield pg
        browser.close()


def test_relative_timetable_and_prices_give_one_capture_with_prices(page):
    query = "&".join(f"connectionIds[]={c['id']}" for c in base.SEARCH["connections"])
    page.evaluate("""([b, q]) => fetch('api/hafas/v4/timetable', {method: 'POST', body: JSON.stringify(b)})
      .then(r => r.json()).then(() => fetch('api/offer/v1/prices?' + q)).then(r => r.json())""",
                  [base.SEARCH_BODY, query])
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    page.wait_for_timeout(300)
    sent = page.evaluate("window.__ingest")
    assert len(sent) == 1
    raw = sent[0]["body"]["raw"]
    assert raw["response"] == base.SEARCH
    assert raw["prices"] == {o["connectionId"]: str(o["price"]) for o in base.PRICES["offers"]}
    assert base.status(page) == f"Captured {base.CONNECTIONS} offers → sent ✓"


def test_capture_with_no_offers_is_not_sent(page):
    page.route(f"{base.SITE}/api/offer/v6/offers", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"offerSections": []}'))
    page.evaluate("() => fetch('api/offer/v6/offers', {method: 'POST', body: '{}'}).then(r => r.text())")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert "sent" not in base.status(page)
