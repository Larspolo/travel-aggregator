"""The auto-select of the trip as a whole in the browser (#722, epic #718): a real server, the real bahn.de fixture of
Amsterdam - Zürich and the real userscripts core.js and bahn.user.js. The bahn.de page is served by the test, and the
panel's requests go to the test server only, through a Python relay (P1)."""

import json
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Capture, Trip
from tests.test_all_pages_look import _launch, _serve

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
BAHN = ROOT / "userscripts" / "bahn.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "bahn.de" / "fahrplan-amsterdam-zuerich.json")
                     .read_text(encoding="utf-8"))
DAY = date(2026, 11, 20)  # the departure day of the fixture
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # no proxy for the test server
SHADOW = "document.getElementById('ta-core-panel').shadowRoot"
STUBS = """
window.__gm = __CFG__;
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_info = () => ({ script: {} });
window.GM_xmlhttpRequest = (d) => {
  const req = JSON.stringify({ method: d.method, url: d.url, headers: d.headers || {},
                               data: d.data === undefined ? null : d.data });
  window.__relay(req).then((r) => d.onload({ status: r.status, responseText: r.text }),
                           () => d.onerror && d.onerror());
};
"""


def _relayer(base):
    """The Python side of GM_xmlhttpRequest: the request goes to the test server, and only there (P1)."""
    def relay(raw):
        req = json.loads(raw)
        if not req["url"].startswith(base):
            raise ValueError(f"not the test server: {req['url']}")
        data = None if req["data"] is None else req["data"].encode("utf-8")
        request = urllib.request.Request(req["url"], data=data, method=req["method"], headers=req["headers"])
        try:
            with OPENER.open(request, timeout=10) as r:
                return {"status": r.status, "text": r.read().decode("utf-8")}
        except urllib.error.HTTPError as err:
            return {"status": err.code, "text": err.read().decode("utf-8")}
    return relay


def _serve_bahn(route):
    url = route.request.url
    if url.endswith("/web/api/angebote/fahrplan"):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(FIXTURE["response"]))
    elif "/web/api/" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"verbindungen": []}))
    else:
        route.fulfill(status=200, content_type="text/html", body="<html><body>bahn.de test page</body></html>")


@pytest.fixture
def server(sessions):
    """The test server with the owner login and a token; the trips are added by each test."""
    with sessions() as s:
        token = tokens.create(s, "test")
    app.dependency_overrides[require_login] = lambda: None
    srv, thread, base = _serve()
    yield base, token
    srv.should_exit = True
    thread.join(5)
    app.dependency_overrides.pop(require_login, None)


def _add_trip(sessions, **fields):
    with sessions() as s:
        t = Trip(**fields)
        s.add(t)
        s.commit()
        return t.id


def _trips(sessions):
    with sessions() as s:
        return [(t.id, t.origin_text, t.destination_text, t.date_from)
                for t in s.scalars(select(Trip).order_by(Trip.id))]


def _captures(sessions, trip_id):
    with sessions() as s:
        return len(s.scalars(select(Capture.id).where(Capture.trip_id == trip_id)).all())


def _page_text(base, trip_id):
    return OPENER.open(f"{base}/trips/{trip_id}", timeout=10).read().decode("utf-8")


def _priced(raw):
    prices = []
    for conn in raw["response"]["verbindungen"]:
        price = conn.get("angebotsPreis") or {}
        if price.get("betrag") is not None:
            prices.append(Decimal(str(price["betrag"])).quantize(Decimal("0.01")))
    return prices


def _status(page):
    return page.evaluate(f"{SHADOW}.querySelector('.panel').textContent")


def _open_bahn(p, base, token, trip_id):
    """A browser on bahn.de (served by the test) with the panel of core.js and the script of bahn.user.js."""
    browser = _launch(p)
    page = browser.new_page()
    page.expose_function("__relay", _relayer(base))
    page.route("https://int.bahn.de/**", _serve_bahn)
    cfg = json.dumps({"server": base, "token": token, "trip": trip_id, "autosend": True})
    page.add_init_script(STUBS.replace("__CFG__", cfg) + CORE.read_text(encoding="utf-8") + "\n"
                         + BAHN.read_text(encoding="utf-8"))
    page.goto("https://int.bahn.de/en/buchung/fahrplan/suche")
    page.wait_for_function(f"() => {SHADOW}.querySelector('select.trip').value === '{trip_id}'")
    return browser, page


def _search(page):
    """The page searches a connection: the userscript captures the fahrplan response and sends it."""
    body = json.dumps(FIXTURE["request"])
    page.evaluate("b => fetch('/web/api/angebote/fahrplan', {method: 'POST', body: b}).then(r => r.json())", body)
    page.wait_for_function(f"() => {SHADOW}.querySelector('.panel').textContent.includes('sent')")


def test_the_capture_goes_to_the_matching_trip_and_the_dropdown_follows_it(sessions, server):
    from playwright.sync_api import sync_playwright

    base, token = server
    matching = _add_trip(sessions, title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                         date_from=DAY, date_to=DAY, status="planning")
    other = _add_trip(sessions, title="Lyon – Madrid", origin_text="Lyon", destination_text="Madrid",
                      date_from=date(2026, 12, 20), date_to=date(2026, 12, 20), status="planning")
    with sync_playwright() as p:
        browser, page = _open_bahn(p, base, token, other)
        try:
            _search(page)
            assert page.evaluate(f"{SHADOW}.querySelector('select.trip').value") == str(matching)
            assert "Amsterdam – Zürich" in _status(page)
        finally:
            browser.close()

    assert _captures(sessions, matching) == 1
    assert _captures(sessions, other) == 0
    own = _page_text(base, matching)
    for price in _priced(FIXTURE):
        assert f"€{price:.2f}" in own, price
    assert "€130.99" not in _page_text(base, other)


def test_no_matching_trip_offers_a_new_trip_with_the_places_and_the_date(sessions, server):
    from playwright.sync_api import sync_playwright

    base, token = server
    only = _add_trip(sessions, title="Lyon – Madrid", origin_text="Lyon", destination_text="Madrid",
                     date_from=date(2026, 12, 20), date_to=date(2026, 12, 20), status="planning")
    with sync_playwright() as p:
        browser, page = _open_bahn(p, base, token, only)
        try:
            _search(page)
            assert "No trip matches: + new trip" in _status(page)
            page.evaluate(f"{SHADOW}.querySelector('.new-trip').click()")
            page.evaluate(f"{SHADOW}.querySelector('.ask-save').click()")
            for _ in range(100):
                if len(_trips(sessions)) == 2:
                    break
                page.wait_for_timeout(100)
        finally:
            browser.close()

    created = [t for t in _trips(sessions) if t[0] != only]
    assert len(created) == 1
    _, origin, destination, day = created[0]
    assert origin == "Amsterdam Centraal"
    assert destination == "Zürich HB"
    assert day == DAY
