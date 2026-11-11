"""The SBB userscript in the browser (#1787): it pairs the GraphQL Trips response of the page with each TripPrices
response of the same trips and sends the pair as one raw capture; the ingest API then shows the connections on the trip
page. Playwright serves all URLs from the test, so the userscript sends no request to sbb.ch (P1)."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.parsers.sbb import SbbParser

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "userscripts" / "core.js"
SBB = ROOT / "userscripts" / "sbb.user.js"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "sbb.ch" / "search-basel-zuerich.json").read_text("utf-8"))
GRAPHQL = "https://graphql.www.sbb.ch/"
PAGE_URL = "https://www.sbb.ch/en"
PRICES = sum(len(t["tripPrices"]) for t in FIXTURE["prices"]["response"]["data"]["tripPrices"])
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Basel'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""
PAGE = "<html><body><p>sbb.ch test page</p></body></html>"
CORS = {"Access-Control-Allow-Origin": "*"}


def query(name, part):
    return json.dumps({"operationName": name, "query": f"query {name} {{ }}", "variables": part["request"]["body"]
                       ["variables"]})


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        requests = []

        def serve(route):
            url = route.request.url
            requests.append(url)
            if url == GRAPHQL:
                name = json.loads(route.request.post_data or "{}").get("operationName")
                body = {"Trips": FIXTURE["response"], "TripPrices": FIXTURE["prices"]["response"]}.get(
                    name, {"data": {"toggle": True}})
                route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(body))
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + CORE.read_text() + "\n" + SBB.read_text())
        pg.goto(PAGE_URL)
        pg.requests = requests
        yield pg
        browser.close()


def post(pg, name, part):
    pg.evaluate("""([u, b]) => fetch(u, {method: 'POST', headers: {'content-type': 'application/json'}, body: b})
      .then(r => r.json())""", [GRAPHQL, query(name, part)])


def status(pg):
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


@pytest.fixture
def client(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Basel - Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def test_the_trips_and_their_prices_are_one_capture_on_the_trip_page(page, client):
    post(page, "Toggle", {"request": {"body": {"variables": {}}}})
    post(page, "Trips", FIXTURE)
    post(page, "TripPrices", FIXTURE["prices"])
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {PRICES} offers → sent ✓"
    sent = page.evaluate("window.__ingest")[0]
    assert sent["url"] == "https://ta.example/api/ingest"
    b = sent["body"]
    assert (b["source"], b["trip_id"], b["parser_version"]) == ("sbb.ch", 5, "1.0.0")
    raw = b["raw"]
    assert {k: raw[k] for k in ("url", "method", "request", "response")} == {
        k: FIXTURE[k] for k in ("url", "method", "request", "response")}
    assert raw["prices"]["request"] == FIXTURE["prices"]["request"]
    assert raw["prices"]["response"] == FIXTURE["prices"]["response"]
    assert "query" not in json.dumps(raw["request"])
    assert set(page.requests) <= {PAGE_URL, GRAPHQL}

    http, auth, trip_id = client
    r = http.post("/api/ingest", headers=auth, json={**b, "trip_id": trip_id})
    assert r.status_code == 200, r.text
    parsed = SbbParser().parse(raw)
    assert r.json()["created"] + r.json()["updated"] + r.json()["unchanged"] == len(parsed.offers)
    html = http.get(f"/trips/{trip_id}").text
    for offer in parsed.offers:
        assert offer.legs[0].depart_at.strftime("%H:%M") in html
        assert offer.legs[-1].arrive_at.strftime("%H:%M") in html


def test_prices_of_other_trips_and_other_queries_are_not_sent(page):
    post(page, "TripPrices", FIXTURE["prices"])  # no Trips response yet
    post(page, "Toggle", {"request": {"body": {"variables": {}}}})
    page.wait_for_timeout(300)
    assert page.evaluate("window.__ingest") == []
