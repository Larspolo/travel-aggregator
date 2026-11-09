"""The userscript queue keeps at most 20 captures: a longer failure of the server drops the oldest ones (#1665)."""

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
  window.__sent.push({url: d.url, body: JSON.parse(d.data), status: window.__status});
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


def payload(i):
    return {"trip_id": 1, "source": "test", "seq": i, "offers": [{"i": 0}]}


def send_down(pg, first, last):
    """Capture payloads first..last while the server is down (no request succeeds)."""
    pg.evaluate("window.__status = 0")
    for i in range(first, last + 1):
        pg.evaluate("p => TACore.send(p)", payload(i))


def test_21st_capture_drops_the_oldest(page):
    send_down(page, 1, 21)
    seqs = [p["seq"] for p in page.evaluate("TACore.queue()")]
    assert len(seqs) == 20
    assert seqs == list(range(2, 22))
    assert "1 old capture dropped" in status(page)


def test_more_drops_are_counted(page):
    send_down(page, 1, 22)
    assert [p["seq"] for p in page.evaluate("TACore.queue()")][0] == 3
    assert status(page).startswith("2 old captures dropped. ")


def test_19_then_20th_drops_nothing(page):
    send_down(page, 1, 20)
    assert len(page.evaluate("TACore.queue()")) == 20
    assert "dropped" not in status(page)


def test_press_send_text_shows_the_drop(page):
    page.evaluate("window.__gm.autosend = false")
    send_down(page, 1, 21)
    assert status(page).startswith("1 old capture dropped. ")
    assert "press Send" in status(page)
    assert len(page.evaluate("TACore.queue()")) == 20
