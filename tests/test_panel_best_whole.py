"""The best offer of a trip over three captures (#882): the ingest responses name the best offer, and the panel shows
the one of the last capture. Playwright stubs GM_xmlhttpRequest, so no request goes to a server or a travel site (P1)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.main import app
from app.models import Trip

CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = { server: 'https://travel.example', token: 'token', trip: 1, autosend: true };
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_info = () => ({ script: {} });
window.__body = '{}';
window.GM_xmlhttpRequest = (o) => {
  setTimeout(() => o.onload({ status: 200, responseText: window.__body }), 0);
};
"""
PAGE = "<html><head></head><body></body></html>"


def offer_body(trip_id, price, service):
    day = datetime.now(UTC).year + 1
    leg = {"mode": "train", "carrier": "DB", "service_no": service, "from_name": "Amsterdam Centraal",
           "to_name": "Basel SBB", "depart_at": f"{day}-12-20T07:34:00+01:00",
           "arrive_at": f"{day}-12-20T14:02:00+01:00"}
    return {
        "trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0",
        "captured_at": "2026-11-03T19:41:00Z", "page_url": "https://www.bahn.de/buchung/fahrplan/suche",
        "search_context": {"from": "Amsterdam", "to": "Zürich", "date": f"{day}-12-20", "travelers": 1},
        "offers": [{"price_amount": price, "price_currency": "EUR", "fare_name": "Sparpreis",
                    "flexibility": "non_refundable", "booking_url": "https://www.bahn.de/buchung/x",
                    "legs": [leg]}],
    }


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id


def three_captures(client, auth, trip_id):
    responses = []
    for price, service in (("120.00", "ICE 101"), ("90.00", "ICE 103"), ("150.00", "ICE 105")):
        r = client.post("/api/ingest", json=offer_body(trip_id, price, service), headers=auth)
        assert r.status_code == 200
        responses.append(r)
    return responses


# `best.total` is the effective cost, not the price: the same itinerary adds a fixed 97.00 here (the ranking
# of the trip, #710). The price decides the order: 120 then 90 then 150.
EFFECTIVE_OFFSET = 97


def best_of(response):
    best = response.json()["best"]
    return best["total"], best["new"]


def test_three_captures_name_the_best_offer_of_each_response(setup):
    client, auth, trip_id = setup
    first, second, third = three_captures(client, auth, trip_id)
    assert best_of(first) == (f"{120 + EFFECTIVE_OFFSET}.00", True)
    assert best_of(second) == (f"{90 + EFFECTIVE_OFFSET}.00", True)
    assert best_of(third) == (f"{90 + EFFECTIVE_OFFSET}.00", False)


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(PAGE)
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
        yield pg
        browser.close()


@pytest.mark.slow
def test_the_panel_shows_the_best_of_the_last_of_three_captures(setup, page):
    client, auth, trip_id = setup
    third = three_captures(client, auth, trip_id)[2]
    # The panel stays on the trip of the captures: a trip_id in the response must not switch it.
    page.evaluate("(id) => { window.__gm.trip = id; }", trip_id)
    page.evaluate("(body) => { window.__body = body; }", json.dumps(third.json()))
    page.evaluate("TACore.send({ source: 'test', offers: [{ price: '1.00' }] })")
    page.wait_for_function("() => document.getElementById('ta-core-panel').shadowRoot"
                           ".querySelector('.panel').textContent.includes('Best of trip')")
    shown = page.evaluate("""() => document.getElementById('ta-core-panel').shadowRoot
        .querySelector('.panel').textContent""")
    assert f"Best of trip: €{90 + EFFECTIVE_OFFSET}" in shown
    assert "(new)" not in shown
