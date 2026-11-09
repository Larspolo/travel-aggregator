"""The Tampermonkey menu sends or discards the queue (#1666)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', queue: []};
window.__menu = [];
window.__fns = {};
window.__sent = [];
window.__status = 200;
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = (name, fn) => { window.__menu.push(name); window.__fns[name] = fn; };
window.GM_xmlhttpRequest = (d) => {
  window.__sent.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: window.__status}), 0);
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


def queue_with(pg, n):
    items = [{"trip_id": 1, "source": "test", "seq": i, "offers": [{"i": 0}]} for i in range(1, n + 1)]
    pg.evaluate("q => { window.__gm.queue = q; }", items)


def test_menu_has_send_and_discard(page):
    assert page.evaluate("window.__menu")[:2] == ["Send now", "Discard the queue"]


def test_send_now_sends_oldest_first(page):
    queue_with(page, 3)
    page.evaluate("window.__fns['Send now']()")
    page.wait_for_function("window.__sent.length === 3")
    assert [s["body"]["seq"] for s in page.evaluate("window.__sent")] == [1, 2, 3]
    assert "sent ✓" in status(page)
    assert page.evaluate("window.__gm.queue") == []


def test_discard_empties_queue_without_request(page):
    queue_with(page, 3)
    page.evaluate("window.__fns['Discard the queue']()")
    assert page.evaluate("window.__gm.queue") == []
    assert status(page) == "Discarded 3 captures"
    assert page.evaluate("window.__sent") == []


def test_discard_empty_queue_says_so(page):
    page.evaluate("window.__fns['Discard the queue']()")
    assert status(page) == "The queue is empty"
    assert page.evaluate("window.__sent") == []
