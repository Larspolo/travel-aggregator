"""No page scrolls sideways at a phone width of 390 px (#312)."""

import os
import socket
import threading
import time

import pytest
import uvicorn
from sqlalchemy import select

from app.models import Itinerary

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

WIDTH = 390


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
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == trip_id).limit(4)).all()
    yield f"http://127.0.0.1:{port}", trip_id, "&".join(f"it={i}" for i in ids)
    server.should_exit = True
    thread.join(5)


def test_no_page_is_wider_than_a_phone(live):
    from playwright.sync_api import sync_playwright

    base, tid, its = live
    paths = ["/", "/upcoming", f"/trips/{tid}", f"/trips/{tid}/compare?{its}", "/profiles", "/places", "/tokens", "/settings",
             f"/trips/{tid}/captures", "/trips/new", f"/trips/{tid}/edit", f"/trips/{tid}/offers/new", "/sources/new", "/login"]
    exe = "/opt/pw-browsers/chromium"
    wide = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": 800})
        for path in paths:
            response = page.goto(base + path)
            assert response.status < 400, path
            width = page.evaluate("document.documentElement.scrollWidth")
            if width > WIDTH:
                wide[path] = width
        browser.close()
    assert wide == {}
