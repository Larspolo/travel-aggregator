"""The bahn.de panel says the number of fares that a capture stores (#1678): a recon response counts its fare
classes, as the parser does; a results page counts one per connection. Playwright serves all URLs (P1)."""

import json
import os
from pathlib import Path

import pytest

from app.parsers.bahn import BahnParser

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
BAHN = ROOT / "userscripts" / "bahn.user.js"
FIX = ROOT / "tests" / "fixtures" / "bahn.de"
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Trip'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""


def _panel_after(fixture, path):
    data = json.loads((FIX / fixture).read_text("utf-8"))
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if route.request.url.endswith(path):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data["response"]))
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>test</body></html>")

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + BAHN.read_text())
        pg.goto("https://int.bahn.de/en/buchung/fahrplan/suche")
        pg.evaluate("p => fetch(p, {method: 'POST', body: '{}'}).then(r => r.json())", path)
        sel = "document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent"
        pg.wait_for_function(f"{sel}.includes('sent')")
        text = pg.evaluate(sel)
        browser.close()
    return text, data


def test_recon_capture_counts_its_fares():
    text, data = _panel_after("recon-169.json", "/web/api/angebote/recon")
    assert len(data["response"]["verbindungen"]) == 1
    assert len(BahnParser().parse(data).offers) == 6
    assert "Captured 6 offers" in text


def test_results_page_counts_one_per_connection():
    text, data = _panel_after("fahrplan-koeln-muenchen.json", "/web/api/angebote/fahrplan")
    assert f"Captured {len(data['response']['verbindungen'])} offers" in text
