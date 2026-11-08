"""The service worker saves the Upcoming page: with no network the app shows its last online copy (#963)."""

import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn

from app.auth import make_password_hash
from app.models import Itinerary, Leg, Trip
from tests.browser_wait import wait_js

pytestmark = pytest.mark.slow
PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10)
CACHED = "caches.open('upcoming-v1').then(c => c.keys()).then(k => k.map(r => new URL(r.url).pathname))"


@pytest.fixture
def live(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 77", from_name="Amsterdam", to_name="Berlin",
                  depart_at=SOON, depart_offset_min=60, arrive_at=SOON + timedelta(hours=2), arrive_offset_min=60)
        trip = Trip(title="Offline trip", origin_text="A", destination_text="B", status="planning")
        trip.itineraries = [Itinerary(fingerprint="x", depart_at=SOON, arrive_at=SOON + timedelta(hours=2),
                                      duration_min=120, booked=True, legs=[leg])]
        s.add(trip)
        s.commit()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        context = browser.new_context()
        yield context.new_page()
        browser.close()


def login(page, live):
    page.goto(live + "/login")
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state()


def test_the_saved_upcoming_page_opens_offline(live, page):
    login(page, live)
    page.goto(live + "/upcoming")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")
    cached = page.evaluate(CACHED)
    assert all(p == "/upcoming" or p.startswith("/static/") for p in cached) and "/static/app.css" in cached
    page.context.set_offline(True)
    page.reload()
    text = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
    assert "Amsterdam → Berlin" in text and "08:12" in text and "IC 77" in text


def test_log_out_deletes_the_saved_upcoming_page(live, page):
    login(page, live)
    page.goto(live + "/upcoming")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")
    page.goto(live + "/logout")
    wait_js(page, "caches.keys().then(k => !k.includes('upcoming-v1'))")
    page.context.set_offline(True)
    page.goto(live + "/upcoming")
    body = page.inner_text("body")
    assert "No saved journeys" in body and "Amsterdam" not in body and "Offline trip" not in body


def test_no_earlier_visit_shows_the_offline_answer(live, page):
    login(page, live)
    # a service worker from another page (as push.js on the settings page), but no visit of /upcoming
    page.evaluate("navigator.serviceWorker.register('/sw.js')")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    page.context.set_offline(True)
    page.goto(live + "/upcoming")
    body = page.inner_text("body")
    assert "No saved journeys" in body and "Amsterdam" not in body and "Offline trip" not in body
    assert "/upcoming" not in page.evaluate(CACHED)
