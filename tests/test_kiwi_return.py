"""Kiwi.com return searches (#1004): the parser reads SearchReturnItinerariesQuery (the outbound flights with the
price of the return ticket), and the userscript sends its response. Playwright serves all URLs (P1)."""

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.kiwi import KiwiParser

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "kiwi.com" / "return-amsterdam-lisbon.json").read_text("utf-8"))
API = "https://api.skypicker.com/umbrella/v2/graphql"


def test_return_search_gives_one_outbound_offer_per_fare():
    r = KiwiParser().parse(FIXTURE)
    itins = FIXTURE["response"]["data"]["returnItineraries"]["itineraries"]
    assert r.errors == []
    assert len(r.offers) == sum(len(it["bookingOptions"]["edges"]) for it in itins) == 5
    first = r.offers[0]
    assert first.price_amount == Decimal("127.00") and first.price_currency == "GBP"
    assert first.fare_name == "KIWI-BASIC return"
    assert [(leg.from_code, leg.to_code) for leg in first.legs] == [("AMS", "LIS")]
    assert first.legs[0].depart_at.isoformat() == "2026-12-01T06:35:00+01:00"
    assert all(leg.depart_at.date().isoformat() == "2026-12-01" for o in r.offers for leg in o.legs)
    assert "searchType=return" in first.booking_url


def test_one_way_fares_have_no_return_suffix():
    raw = json.loads((ROOT / "tests" / "fixtures" / "kiwi.com" / "search-amsterdam-lisbon.json").read_text("utf-8"))
    assert not any((o.fare_name or "").endswith("return") for o in KiwiParser().parse(raw).offers)


def test_return_fixture_has_no_tokens():
    text = json.dumps(FIXTURE)
    assert "token=REDACTED" in text and "serverToken" not in text and "@" not in text


@pytest.mark.slow
def test_userscript_sends_a_return_search():
    playwright = pytest.importorskip("playwright.sync_api")
    stubs = """
    window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
    window.__ingest = [];
    window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
    window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
    window.GM_registerMenuCommand = () => {};
    window.GM_xmlhttpRequest = (d) => {
      if (d.url.startsWith('https://ta.example/api/trips')) {
        setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'Lisbon'}])}), 0);
        return;
      }
      window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
      setTimeout(() => d.onload({status: 200}), 0);
    };
    """
    script = stubs + (ROOT / "userscripts" / "core.js").read_text() + "\n" + (ROOT / "userscripts" / "kiwi.user.js").read_text()
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if route.request.url.startswith(API):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(FIXTURE["response"]))
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>kiwi</body></html>")

        pg.route("**/*", serve)
        pg.add_init_script(script)
        pg.goto("https://www.kiwi.com/en/search/results/amsterdam-netherlands/lisbon-portugal/2026-12-01/2026-12-08/")
        request = {"variables": {"options": {"currency": "gbp"},
                                 "search": {"passengers": {"adults": 1, "children": 0, "infants": 0}}}}
        pg.evaluate("([u, b]) => fetch(u, {method: 'POST', body: b}).then(r => r.json())",
                    [API + "?featureName=SearchReturnItinerariesQuery", json.dumps(request)])
        pg.wait_for_function("window.__ingest.length === 1")
        body = pg.evaluate("window.__ingest")[0]["body"]
        browser.close()
    assert (body["source"], body["parser_version"]) == ("kiwi.com", "1.2.0")
    assert body["raw"] == {"currency": "gbp", "passengers": {"adults": 1, "children": 0, "infants": 0},
                           "response": FIXTURE["response"]}
