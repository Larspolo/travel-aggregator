"""The userscript core sends payloads to the server and keeps failed ones in a queue (#33)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok'};
window.__menu = [];
window.__sent = [];
window.__status = 200;
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = (name) => { window.__menu.push(name); };
window.GM_xmlhttpRequest = (d) => {
  window.__sent.push({url: d.url, auth: d.headers.Authorization, body: JSON.parse(d.data), status: window.__status});
  setTimeout(() => (window.__status === 0 ? d.onerror({}) : d.onload({status: window.__status})), 0);
};
"""


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<html><body></body></html>")
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text())
        yield pg
        browser.close()


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def payload(i, n=2):
    return {"trip_id": 1, "source": "test", "seq": i, "offers": [{"i": k} for k in range(n)]}


def test_menu_entries(page):
    assert page.evaluate("window.__menu") == ["Set server URL", "Set API token", "Add this website"]


def test_200_shows_sent(page):
    page.evaluate("p => TACore.send(p)", payload(1, 3))
    sent = page.evaluate("window.__sent")
    assert sent[-1]["url"] == "https://ta.example/api/ingest"
    assert sent[-1]["auth"] == "Bearer tok"
    assert status(page) == "Captured 3 offers → sent ✓"
    assert page.evaluate("TACore.queue()") == []


def test_failed_sends_retry_in_order(page):
    page.evaluate("window.__status = 0")
    page.evaluate("p => TACore.send(p)", payload(1))
    page.evaluate("window.__status = 503")
    page.evaluate("p => TACore.send(p)", payload(2))
    page.evaluate("p => TACore.send(p)", payload(3))
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [1, 2, 3]
    assert "kept in the queue" in status(page)
    page.evaluate("window.__status = 200; window.__sent = []")
    page.evaluate("TACore.flush()")
    assert [s["body"]["seq"] for s in page.evaluate("window.__sent")] == [1, 2, 3]
    assert page.evaluate("TACore.queue()") == []


def test_401_keeps_payload(page):
    page.evaluate("window.__status = 401")
    page.evaluate("p => TACore.send(p)", payload(7))
    assert status(page) == "Check the API token"
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [7]


def test_other_4xx_drops(page):
    page.evaluate("window.__status = 422")
    page.evaluate("p => TACore.send(p)", payload(8))
    assert "dropped" in status(page)
    assert page.evaluate("TACore.queue()") == []


def test_only_configured_host(page):
    page.evaluate("window.__status = 0")
    page.evaluate("p => TACore.send(p)", payload(1))
    page.evaluate("TACore.flush()")
    assert {s["url"] for s in page.evaluate("window.__sent")} == {"https://ta.example/api/ingest"}
