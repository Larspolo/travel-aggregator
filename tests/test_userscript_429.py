"""A 429 (too many requests) keeps the payload in the queue; it is sent again later (#413)."""

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


def test_429_keeps_payload(page):
    page.evaluate("window.__status = 429")
    page.evaluate("p => TACore.send(p)", payload(5))
    assert status(page) == "Server busy: kept in the queue"
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [5]


def test_429_then_200_sends_payload(page):
    page.evaluate("window.__status = 429")
    page.evaluate("p => TACore.send(p)", payload(6))
    page.evaluate("window.__status = 200; window.__sent = []")
    page.evaluate("TACore.flush()")
    assert [s["body"]["seq"] for s in page.evaluate("window.__sent")] == [6]
    assert page.evaluate("TACore.queue()") == []


def test_429_stops_flush_at_first_retry(page):
    page.evaluate("window.__status = 429")
    page.evaluate("p => TACore.send(p)", payload(1))
    page.evaluate("p => TACore.send(p)", payload(2))
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [1, 2]
    assert len(page.evaluate("window.__sent")) == 2  # one request per send; flush stopped at 429
    page.evaluate("window.__sent = []; TACore.flush()")
    assert len(page.evaluate("window.__sent")) == 1
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [1, 2]


def test_other_4xx_drops(page):
    page.evaluate("window.__status = 422")
    page.evaluate("p => TACore.send(p)", payload(8))
    assert "dropped" in status(page)
    assert page.evaluate("TACore.queue()") == []
