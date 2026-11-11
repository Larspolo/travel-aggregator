"""The whole offline Upcoming page (#1002, epic #962): each part of the online page shows on the saved page, or says that it
needs a network; the service worker saves no other page, no API answer and no token."""

import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn

from app.auth import make_password_hash
from app.models import Itinerary, Leg, Trip
from tests.browser_wait import wait_js
from tests.test_upcoming_offline import CACHED, PASSWORD, login
import tests.test_upcoming_offline as offline

page = offline.page  # the browser fixture of the Upcoming offline tests

pytestmark = pytest.mark.slow
NEEDS_NETWORK = "Add to calendar: needs a network"
DAY = (datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10))
ALL_CACHED = ("caches.keys().then(ks => Promise.all(ks.map(k => caches.open(k).then(c => c.keys())))"
              ".then(list => list.flat().map(r => new URL(r.url).pathname + new URL(r.url).search)))")


def _leg(seq, depart, arrive, carrier, number, frm, to):
    return Leg(seq=seq, mode="train", carrier=carrier, service_no=number, from_name=frm, to_name=to,
               depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)


@pytest.fixture
def live(sessions, monkeypatch):
    """The server with two booked journeys: a direct one, and one with two legs that arrives on the next day."""
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        direct = _leg(0, DAY, DAY + timedelta(hours=2), "NS", "IC 77", "Amsterdam", "Berlin")
        late_d = DAY + timedelta(hours=15, minutes=18)  # 22:30 local
        late_a1 = late_d + timedelta(hours=1)
        second = _leg(0, late_d, late_a1, "NS", "IC 12", "Amsterdam", "Utrecht")
        third = _leg(1, late_a1 + timedelta(minutes=10), late_d + timedelta(hours=10, minutes=35), "DB", "ICE 9",
                     "Utrecht", "Berlin")  # arrives 07:05 on the next day
        trip = Trip(title="Offline trip", origin_text="A", destination_text="B", status="planning")
        trip.itineraries = [
            Itinerary(fingerprint="direct", depart_at=DAY, arrive_at=DAY + timedelta(hours=2), duration_min=120,
                      booked=True, legs=[direct]),
            Itinerary(fingerprint="late", depart_at=late_d, arrive_at=late_d + timedelta(hours=10, minutes=35),
                      duration_min=635, booked=True, legs=[second, third]),
        ]
        s.add(trip)
        s.commit()
        trip_id = trip.id
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", trip_id
    server.should_exit = True
    thread.join(5)


def _main_text(page):
    return page.inner_text("main") if page.locator("main").count() else page.inner_text("body")


def _without_note(text):
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line and not line.startswith("Offline: saved at")]


def test_offline_page_equals_the_online_page_and_calendar_needs_network(live, page):
    base, trip_id = live
    login(page, base)
    page.goto(base + "/upcoming")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")
    online = _main_text(page)
    assert "Amsterdam → Berlin" in online and "+1 day" in online and "IC 77" in online and "ICE 9" in online

    # visit the other pages online, and one API answer: none of them may be saved
    for path in ["/trips", f"/trips/{trip_id}", "/settings"]:
        page.goto(base + path)
    page.evaluate("fetch('/api/health').then(r => r.text())")
    page.goto(base + "/upcoming")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming'))")

    page.context.set_offline(True)
    page.reload()
    wait_js(page, "document.querySelector('a[download]').getAttribute('aria-disabled') === 'true'")
    offline_text = _main_text(page)
    assert _without_note(offline_text) == _without_note(online)
    assert "Offline: saved at" in offline_text
    links = page.locator("a[download]")
    assert links.count() == 2  # one calendar link per journey
    for i in range(links.count()):
        assert links.nth(i).get_attribute("aria-disabled") == "true"
        assert links.nth(i).get_attribute("aria-label") == NEEDS_NETWORK

    page.context.set_offline(False)
    wait_js(page, "!document.querySelector('a[download]').hasAttribute('aria-disabled')")
    assert page.locator("a[download]").first.get_attribute("aria-label") == "Add to calendar"

    cached = page.evaluate(ALL_CACHED)
    assert cached, "the service worker saved nothing"
    for path in cached:
        assert "?" not in path and not path.startswith("/api/"), path
        assert path == "/upcoming" or path.startswith("/static/"), path
    assert "/upcoming" in cached
