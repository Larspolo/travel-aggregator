"""The bahn.de userscript sends the day price responses of a search with "Bestpreise anzeigen" (#1199). They have no
`verbindungen`, only `intervalle`. Playwright serves all URLs from the test, so no request goes to bahn.de (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
BAHN = ROOT / "userscripts" / "bahn.user.js"
DAY = json.loads((ROOT / "tests" / "fixtures" / "bahn.de" / "tagesbestpreis-amsterdam-zuerich-2026-12-01.json")
                 .read_text("utf-8"))
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Zürich'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""
PAGE = "<html><body><p>bahn.de test page</p></body></html>"


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
            if url.endswith("/web/api/angebote/tagesbestpreis"):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(DAY["response"]))
            elif "/web/api/" in url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"intervalle": []}))
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + BAHN.read_text())
        pg.goto("https://int.bahn.de/en/buchung/fahrplan/suche")
        pg.requests = requests
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def test_day_price_response_is_sent_with_source_bahn(page):
    page.evaluate("b => fetch('/web/api/angebote/tagesbestpreis', {method: 'POST', body: b}).then(r => r.json())",
                  json.dumps(DAY["request"]))
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("bahn.de", 5, "1.2.0")
    assert b["raw"]["response"] == DAY["response"]
    assert b["raw"]["request"] == DAY["request"]
    assert b["raw"]["method"] == "POST"
    assert all(u.startswith("https://int.bahn.de/") for u in page.requests)


def test_other_path_of_angebote_is_not_sent(page):
    page.evaluate("""() => fetch('/web/api/angebote/preisliste', {method: 'POST', body: '{}'})
      .then(r => r.json())""")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
    assert "sent" not in status(page)
