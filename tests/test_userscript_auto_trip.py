"""The panel selects the trip of the ingest response and fills "+ new trip" from its suggestion (#721). Playwright
stubs GM_xmlhttpRequest, so no request goes to a server or a travel site (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = Object.assign({ server: 'https://travel.example', token: 'token', trip: 1, autosend: true },
                            window.__extra || {});
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_info = () => ({ script: {} });
window.__requests = [];
window.__body = '{}';
window.GM_xmlhttpRequest = (o) => {
  window.__requests.push({ method: o.method, url: o.url, data: o.data === undefined ? null : JSON.parse(o.data) });
  let text = window.__body;
  if (o.url.endsWith('/api/trips?status=planning')) text = JSON.stringify([{ id: 1, title: 'Amsterdam – Zürich' }]);
  else if (o.method === 'POST' && o.url.endsWith('/api/trips')) text = JSON.stringify({ id: 9, title: 'New' });
  setTimeout(() => o.onload({ status: 200, responseText: text }), 0);
};
"""
PAGE = "<html><head></head><body></body></html>"
SHADOW = "document.getElementById('ta-core-panel').shadowRoot"


def _open(extra):
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    p = playwright.sync_playwright().start()
    browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
    pg = browser.new_page()
    pg.set_content(PAGE)
    pg.add_script_tag(content=f"window.__extra = {json.dumps(extra)};")
    pg.add_script_tag(content=STUBS)
    pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
    pg.wait_for_function(f"() => {SHADOW}.querySelector('select.trip').options.length > 1")
    return p, browser, pg


@pytest.fixture
def page():
    p, browser, pg = _open({})
    yield pg
    browser.close()
    p.stop()


@pytest.fixture
def page_off():
    p, browser, pg = _open({"autotrip": False})
    yield pg
    browser.close()
    p.stop()


def _send(pg, body):
    pg.evaluate("(body) => { window.__body = body; }", json.dumps(body))
    pg.evaluate("TACore.send({ source: 'test', offers: [{ price: '1.00' }] })")
    pg.wait_for_function(f"() => {SHADOW}.querySelector('.panel').textContent.includes('sent')")


def _ingest_payloads(pg):
    return [r["data"] for r in pg.evaluate("window.__requests") if r["url"].endswith("/api/ingest")]


def _status(pg):
    return pg.evaluate(f"{SHADOW}.querySelector('.panel').textContent")


def test_the_payload_has_auto_trip_and_the_dropdown_follows_the_trip_of_the_response(page):
    assert page.evaluate(f"{SHADOW}.querySelector('.autotrip').checked") is True
    _send(page, {"accepted": 1, "trip_id": 7, "trip_title": "Utrecht – Paris", "suggestion": None})
    assert _ingest_payloads(page)[0]["auto_trip"] is True
    assert page.evaluate(f"{SHADOW}.querySelector('select.trip').value") == "7"
    assert page.evaluate("window.__gm.trip") == 7
    assert _status(page) == "Captured 1 offers → sent to Utrecht – Paris ✓"


def test_new_trip_after_a_suggestion_posts_the_suggested_places_and_date(page):
    suggestion = {"title": "Amsterdam → Lyon", "origin_text": "Amsterdam", "destination_text": "Lyon",
                  "date_from": "2026-12-20"}
    _send(page, {"accepted": 1, "trip_id": 1, "warning": "x", "suggestion": suggestion})
    assert "No trip matches: + new trip" in _status(page)
    page.evaluate(f"{SHADOW}.querySelector('.new-trip').click()")
    prompts = [page.evaluate(f"{SHADOW}.querySelector('.ask-input').value")]
    page.evaluate(f"(() => {{ {SHADOW}.querySelector('.ask-input').value = 'Lyon trip'; "
                  f"{SHADOW}.querySelector('.ask-save').click(); }})()")
    page.wait_for_function("() => window.__requests.some((r) => r.method === 'POST' && r.url.endsWith('/api/trips'))")
    post = [r for r in page.evaluate("window.__requests") if r["method"] == "POST" and r["url"].endswith("/api/trips")]
    assert prompts == ["Amsterdam → Lyon"]
    assert post[0]["data"] == {**suggestion, "title": "Lyon trip"}
    assert all(r["url"].startswith("https://travel.example/") for r in page.evaluate("window.__requests"))


def test_with_auto_select_off_the_payload_has_no_auto_trip(page_off):
    assert page_off.evaluate(f"{SHADOW}.querySelector('.autotrip').checked") is False
    _send(page_off, {"accepted": 1, "trip_id": 1})
    assert "auto_trip" not in _ingest_payloads(page_off)[0]
