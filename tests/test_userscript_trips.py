"""The userscript panel has a trip dropdown, a "+ new trip" action and an auto-send toggle (#56)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = JSON.parse(localStorage.getItem('gm') || '{"server": "https://ta.example"}');
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; localStorage.setItem('gm', JSON.stringify(window.__gm)); };
window.__requests = [];
window.__trips = [{id: 3, title: "Berlin"}, {id: 7, title: "Paris"}];
window.GM_xmlhttpRequest = (d) => {
  window.__requests.push({method: d.method, url: d.url, data: d.data});
  let body = "{}", status = 202;
  if (d.url.includes("/api/trips") && d.method === "GET") { body = JSON.stringify(window.__trips); status = 200; }
  if (d.url.includes("/api/trips") && d.method === "POST") {
    const t = {id: 11, title: JSON.parse(d.data).title}; window.__trips.push(t);
    body = JSON.stringify(t); status = 201;
  }
  setTimeout(() => d.onload({status, responseText: body}), 0);
};
"""
PAYLOAD = {"source": "test", "offers": [{"a": 1}]}


@pytest.fixture
def browser_page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.route("https://ta.test/", lambda r: r.fulfill(body="<html><body></body></html>",
                                                       content_type="text/html"))

        def load():
            pg.goto("https://ta.test/")
            pg.add_script_tag(content=STUBS)
            pg.add_script_tag(content=CORE.read_text())
            pg.wait_for_function("document.getElementById('ta-core-panel').shadowRoot"
                                 ".querySelector('.trip').options.length > 1")

        load()
        yield pg, load
        browser.close()


def ctl(pg, sel):
    return f"document.getElementById('ta-core-panel').shadowRoot.querySelector('{sel}')"


def ingests(pg):
    return [json.loads(r["data"]) for r in pg.evaluate("window.__requests") if r["url"].endswith("/api/ingest")]


def test_dropdown_filled_and_choice_kept_after_reload(browser_page):
    pg, load = browser_page
    assert pg.evaluate(f"[...{ctl(pg, '.trip')}.options].map(o => o.textContent)") == ["(choose)", "Berlin", "Paris"]
    pg.evaluate(f"(() => {{ const s = {ctl(pg, '.trip')}; s.value = '7'; s.dispatchEvent(new Event('change')); }})()")
    load()
    assert pg.evaluate(f"{ctl(pg, '.trip')}.value") == "7"
    assert pg.evaluate("TACore.tripId()") == 7


def test_new_trip_posts_and_selects(browser_page):
    pg, _ = browser_page
    pg.evaluate(f"{ctl(pg, '.new-trip')}.click()")
    pg.evaluate(f"(() => {{ {ctl(pg, '.ask-input')}.value = 'Rome'; {ctl(pg, '.ask-save')}.click(); }})()")
    pg.wait_for_function(f"{ctl(pg, '.trip')}.value === '11'")
    post = [r for r in pg.evaluate("window.__requests") if r["method"] == "POST" and "/api/trips" in r["url"]]
    assert json.loads(post[0]["data"]) == {"title": "Rome"}
    assert pg.evaluate("TACore.tripId()") == 11


def test_auto_send_on_by_default_uses_trip(browser_page):
    pg, _ = browser_page
    assert pg.evaluate(f"{ctl(pg, '.autosend')}.checked") is True
    pg.evaluate("TACore.gm.setValue('trip', 3)")
    pg.evaluate(f"TACore.send({json.dumps(PAYLOAD)})")
    assert ingests(pg)[0]["trip_id"] == 3
    assert pg.evaluate("TACore.queue().length") == 0


def test_manual_send_waits_for_send_button(browser_page):
    pg, _ = browser_page
    pg.evaluate("TACore.gm.setValue('trip', 7)")
    pg.evaluate(f"(() => {{ const c = {ctl(pg, '.autosend')}; c.checked = false; c.dispatchEvent(new Event('change')); }})()")
    pg.evaluate(f"TACore.send({json.dumps(PAYLOAD)})")
    assert ingests(pg) == [] and pg.evaluate("TACore.queue().length") == 1
    pg.evaluate(f"{ctl(pg, '.send')}.click()")
    pg.wait_for_function("TACore.queue().length === 0")
    assert ingests(pg)[0]["trip_id"] == 7


def test_no_trip_keeps_payload_in_queue(browser_page):
    pg, _ = browser_page
    pg.evaluate(f"TACore.send({json.dumps(PAYLOAD)})")
    assert ingests(pg) == [] and pg.evaluate("TACore.queue().length") == 1
