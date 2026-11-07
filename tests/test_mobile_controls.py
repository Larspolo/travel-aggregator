"""The controls of the trip page are at least 40 px high at a phone width of 390 px (#313)."""

import os
import socket
import threading
import time

import pytest
import uvicorn
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

WIDTH = 390
MIN_HEIGHT = 40

# Open every <details> so that the controls inside "Advanced" and "Legs and fares" are measured too.
SMALL_CONTROLS = """() => {
  document.querySelectorAll('details').forEach(d => d.open = true);
  return [...document.querySelectorAll('input, select, button, textarea')]
    .filter(e => e.type !== 'hidden' && e.offsetParent !== null)
    .map(e => [e.outerHTML.slice(0, 90), e.getBoundingClientRect().height])
    .filter(([_, h]) => h < %d);
}""" % MIN_HEIGHT


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
    yield f"http://127.0.0.1:{port}", trip_id
    server.should_exit = True
    thread.join(5)


def _launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


def test_trip_page_controls_are_big_enough_on_a_phone(live):
    from playwright.sync_api import sync_playwright

    base, tid = live
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": WIDTH, "height": 800})
        response = page.goto(f"{base}/trips/{tid}")
        assert response.status < 400
        small = page.evaluate(SMALL_CONTROLS)
        browser.close()
    assert small == []
