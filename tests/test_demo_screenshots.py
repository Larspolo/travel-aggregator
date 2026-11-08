"""Screenshots of all pages with realistic demo offers: trains, a night bus and flights from 3 sources (#660).

The look tests use 20 equal rows to check the row height; these screenshots show how a real trip looks.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Itinerary
from tests.test_all_pages_look import DESKTOP, PHONE, _launch, _serve
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow


def _leg(mode, carrier, no, a, b, dep, arr):
    return {"mode": mode, "carrier": carrier, "service_no": no, "from_name": a, "to_name": b,
            "depart_at": f"2026-12-{dep}+01:00", "arrive_at": f"2026-12-{arr}+01:00"}


def _offer(price, fare, flex, legs):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": fare, "flexibility": flex,
            "booking_url": "https://example.org/book", "legs": legs}


AMS, ZRH = "Amsterdam Centraal", "Zürich HB"
BAHN = [
    _offer(139.90, "Flexpreis", "flexible", [_leg("train", "DB", "ICE 105", AMS, "Basel SBB", "20T07:34", "20T14:02"),
                                             _leg("train", "SBB", "IC 61", "Basel SBB", ZRH, "20T14:33", "20T15:26")]),
    _offer(79.90, "Sparpreis", "non_refundable", [
        _leg("train", "NS", "ICE 121", AMS, "Frankfurt (Main) Hbf", "20T06:00", "20T10:01"),
        _leg("train", "DB", "ICE 375", "Frankfurt (Main) Hbf", "Basel SBB", "20T10:13", "20T13:06"),
        _leg("train", "SBB", "IR 36", "Basel SBB", ZRH, "20T13:28", "20T14:42")]),
    _offer(169.00, "Flexpreis", "flexible", [_leg("train", "DB", "ICE 15", AMS, ZRH, "20T09:00", "20T16:58")]),
]
FLIX = [_offer(44.99, "Standard", "non_refundable",
               [_leg("bus", "FlixBus", "N1720", "Amsterdam Sloterdijk", "Zürich Sihlquai", "20T19:30", "21T08:15")])]
KIWI = [
    _offer(118.00, "Basic", "non_refundable",
           [_leg("flight", "KLM", "KL1957", "Amsterdam Schiphol", "Zürich Airport", "20T08:40", "20T10:05")]),
    _offer(96.00, "Light", "non_refundable", [
        _leg("flight", "easyJet", "U21443", "Amsterdam Schiphol", "Basel EuroAirport", "20T13:15", "20T14:35"),
        _leg("train", "SBB", "IC 3", "Basel SBB", ZRH, "20T15:33", "20T16:26")]),
]


def _capture(source, offers, age):
    at = (datetime.now(timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"source": source, "parser_version": "1.0.0", "captured_at": at, "page_url": "https://example.org/search",
            "search_context": {"from": "Amsterdam", "to": "Zürich", "date": "2026-12-20", "travelers": 1},
            "offers": offers}


def test_demo_screenshots(trip, sessions, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    for source, offers, age in (("bahn.de", BAHN, timedelta(hours=1)), ("flixbus", FLIX, timedelta(hours=2)),
                                ("kiwi", KIWI, timedelta(days=3))):  # kiwi: older than the stale limit
        r = client.post("/api/ingest", json={"trip_id": tid, **_capture(source, offers, age)}, headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["rejected"] == 0, r.json()
    with sessions() as s:
        a, b = [i.id for i in s.query(Itinerary).filter_by(trip_id=tid).order_by(Itinerary.id).limit(2)]
    pages = [("trips", "/"), ("archive", "/?archived=1"), ("trip", f"/trips/{tid}"), ("trip-new", "/trips/new"),
             ("trip-edit", f"/trips/{tid}/edit"), ("trip-delete", f"/trips/{tid}/delete"),
             ("offer-new", f"/trips/{tid}/offers/new"), ("source-new", "/sources/new"), ("captures", "/captures"),
             ("trip-captures", f"/trips/{tid}/captures"), ("profiles", "/profiles"), ("places", "/places"),
             ("settings", "/settings"), ("messages", "/settings/messages"), ("rates", "/rates"), ("tokens", "/tokens"),
             ("compare", f"/trips/{tid}/compare?it={a}&it={b}"),
             ("history", f"/trips/{tid}/itineraries/{a}/history"), ("login", "/login")]
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    server, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            for scheme in ("light", "dark"):
                for width in (DESKTOP, PHONE):
                    ctx = browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme,
                                              device_scale_factor=2)
                    page = ctx.new_page()
                    for name, path in pages:
                        assert page.goto(base + path).status < 400, path
                        page.screenshot(path=os.path.join(shots, f"demo-{name}-{width}-{scheme}.png"),
                                        full_page=True)
                    page.goto(base + f"/trips/{tid}")
                    text = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
                    for word in ("FlixBus", "KLM", "+1 day", "stale"):
                        assert word in text, word
                    page.evaluate("document.querySelector('#table tr.detail details').open = true;"
                                  "document.querySelector('details.more').open = true")
                    page.screenshot(path=os.path.join(shots, f"demo-trip-open-{width}-{scheme}.png"), full_page=True)
                    ctx.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
