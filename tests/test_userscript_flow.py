"""The whole userscript core in the browser: trip choice, auto-send, a failed send and its retry (#58)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', autosend: false};
window.__ingest = [];
window.__answers = [500, 200];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    const text = JSON.stringify([{id: 4, title: 'Other'}, {id: 5, title: 'Zürich'}]);
    setTimeout(() => d.onload({status: 200, responseText: text}), 0);
    return;
  }
  const status = window.__answers.length ? window.__answers.shift() : 200;
  window.__ingest.push({url: d.url, body: JSON.parse(d.data), status});
  setTimeout(() => d.onload({status}), 0);
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


def panel(pg, selector):
    return f"document.getElementById('ta-core-panel').shadowRoot.querySelector('{selector}')"


def status(pg):
    return pg.evaluate(panel(pg, ".panel") + ".textContent")


def test_failed_send_stays_in_queue_and_retry_sends_it_once(page):
    page.wait_for_function(panel(page, ".trip") + ".options.length === 3")
    page.evaluate(f"(() => {{ const s = {panel(page, '.trip')}; s.value = '5'; s.dispatchEvent(new Event('change')); }})()")
    assert page.evaluate("TACore.tripId()") == 5
    assert page.evaluate(panel(page, ".autosend") + ".checked") is False

    offers = [{"i": 0}, {"i": 1}]
    page.evaluate("TACore.report(2)")
    assert status(page) == "Captured 2 offers"
    page.evaluate("o => TACore.send({trip_id: 0, source: 'test', offers: o})", offers)
    assert "press Send" in status(page) and page.evaluate("window.__ingest") == []

    page.evaluate(f"(() => {{ const c = {panel(page, '.autosend')}; c.checked = true; c.dispatchEvent(new Event('change')); }})()")
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function(panel(page, ".panel") + ".textContent.includes('kept in the queue')")
    assert page.evaluate(panel(page, ".panel") + ".className") == "panel error"
    assert [q["offers"] for q in page.evaluate("TACore.queue()")] == [offers]

    page.evaluate("TACore.flush()")
    assert status(page) == "Captured 2 offers → sent ✓"
    assert page.evaluate("TACore.queue()") == []
    sent = page.evaluate("window.__ingest")
    assert [s["status"] for s in sent] == [500, 200]
    assert all(s["body"]["trip_id"] == 5 and s["body"]["offers"] == offers for s in sent)
