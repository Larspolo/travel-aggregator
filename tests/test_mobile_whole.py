"""The mobile feature works on every page: no sideways scroll at 390 px and 1280 px, and big controls (#314)."""

import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_mobile_controls import SMALL_CONTROLS
from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

PHONE = 390
DESKTOP = 1280


@pytest.fixture
def live(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer(f"{80 + i}.90", f"ICE {100 + i}", carrier=f"Carrier number {i}",
                                         fare=f"A long fare name number {i}") for i in range(20)])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    with sessions() as s:
        its = [i.id for i in s.query(Itinerary).filter_by(trip_id=trip_id).order_by(Itinerary.id).limit(2)]
    yield f"http://127.0.0.1:{port}", trip_id, its
    server.should_exit = True
    thread.join(5)


def _launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


def test_every_page_fits_both_widths_and_the_phone_controls_are_big(live):
    from playwright.sync_api import sync_playwright

    base, tid, (first, second) = live
    paths = ["/", f"/trips/{tid}", f"/trips/{tid}/captures", "/profiles", "/places", "/tokens", "/settings",
             "/trips/new", f"/trips/{tid}/edit", f"/trips/{tid}/offers/new", "/sources/new", "/login",
             f"/trips/{tid}/delete", "/captures", "/rates", f"/trips/{tid}/compare?it={first}&it={second}",
             f"/trips/{tid}/itineraries/{first}/history"]
    wide = {}
    small = None
    with sync_playwright() as p:
        browser = _launch(p)
        for width in (PHONE, DESKTOP):
            page = browser.new_page(viewport={"width": width, "height": 800})
            for path in paths:
                response = page.goto(base + path)
                assert response.status < 400, path
                scroll = page.evaluate("document.documentElement.scrollWidth")
                if scroll > width:
                    wide[(width, path)] = scroll
                if width == PHONE and path == f"/trips/{tid}":
                    small = page.evaluate(SMALL_CONTROLS)
            page.close()
        browser.close()
    assert wide == {}
    assert small == []
