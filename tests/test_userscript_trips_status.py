"""The trip dropdown of the userscript panel asks the app for the trips with the status `planning` (#495).

The panel's request goes to the real app: a trip with the status `planning` must be in the answer."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.main import app

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = JSON.parse(localStorage.getItem('gm') || '{"server": "https://ta.example"}');
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; localStorage.setItem('gm', JSON.stringify(window.__gm)); };
window.__requests = [];
window.GM_xmlhttpRequest = (d) => {
  window.__requests.push({method: d.method, url: d.url, data: d.data});
  let body = "{}", status = 202;
  if (d.url.includes("/api/trips") && d.method === "GET") { body = "[]"; status = 200; }
  if (d.url.includes("/api/trips") && d.method === "POST") { body = "{}"; status = 201; }
  setTimeout(() => d.onload({status, responseText: body}), 0);
};
"""


@pytest.fixture
def panel_request():
    """Load the panel with the stubs and return the URL of its first GET to /api/trips."""
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.route("https://ta.test/", lambda r: r.fulfill(body="<html><body></body></html>",
                                                       content_type="text/html"))
        pg.goto("https://ta.test/")
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text())
        pg.wait_for_function("document.getElementById('ta-core-panel') !== null")
        pg.wait_for_function("window.__requests.some(r => r.method === 'GET' && r.url.includes('/api/trips'))")
        requests = pg.evaluate("window.__requests")
        browser.close()
    gets = [r["url"] for r in requests if r["method"] == "GET" and "/api/trips" in r["url"]]
    return gets[0]


def test_panel_asks_for_planning_trips_and_gets_them(sessions, panel_request):
    with sessions() as s:
        token = tokens.create(s, "test")
    c = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    made = c.post("/api/trips", json={"title": "Lisbon"}, headers=auth)
    assert made.status_code == 201 and made.json()["status"] == "planning"

    parts = urlsplit(panel_request)
    assert parts.path == "/api/trips"
    got = c.get(parts.path + ("?" + parts.query if parts.query else ""), headers=auth)
    assert got.status_code == 200
    assert [t["id"] for t in got.json()] == [made.json()["id"]], panel_request
