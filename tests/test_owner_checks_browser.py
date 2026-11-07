"""The steps of the owner checks #368, #369, #377 and #439, done with real clicks in Chromium, so that no person checks
them (owner, 2026-11-07). Only the steps that need a person stay on those tickets.

Set SHOTS=<folder> to keep a screenshot of each check for the evidence comment."""

import copy
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import ingest as ingest_module
from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Trip
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer

pytestmark = pytest.mark.slow

PASSWORD = "pw"
FIXTURES = Path(__file__).parent / "fixtures" / "bahn.de"
GOOD = FIXTURES / "fahrplan-amsterdam-bern-night.json"
BROKEN = FIXTURES / "fahrplan-koeln-muenchen-bahncard25.json"
REASON = "site format changed"


class UnreadableParser:
    source, version = "bahn.de", "0.0.1"

    def parse(self, raw):
        raise ValueError(REASON)


@pytest.fixture
def live(sessions, monkeypatch):
    """A server with the owner password, a token and the trip "Amsterdam – Zürich"; a logged-in browser page."""
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
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
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium"
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base + "/login")
        page.fill('input[name="password"]', PASSWORD)
        page.press('input[name="password"]', "Enter")
        page.wait_for_url(base + "/")
        yield page, base, {"Authorization": f"Bearer {token}"}, trip_id
        browser.close()
    server.should_exit = True
    thread.join(5)


def send(auth, trip_id, offers=None, raw=None):
    """POST /api/ingest, as a userscript does."""
    if raw is None:
        body = copy.deepcopy(BODY)
        body.update(trip_id=trip_id, offers=offers)
    else:
        body = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = TestClient(app).post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def shot(page, name):
    if os.environ.get("SHOTS"):
        page.screenshot(path=os.path.join(os.environ["SHOTS"], f"{name}.png"), full_page=True)


def test_377_find_the_failed_captures(live, monkeypatch):
    page, base, auth, tid = live
    send(auth, tid, raw=json.loads(GOOD.read_text(encoding="utf-8")))
    with monkeypatch.context() as m:
        m.setattr(ingest_module, "get_parser", lambda source: UnreadableParser())
        send(auth, tid, raw=json.loads(BROKEN.read_text(encoding="utf-8")))

    # 1. "Captures" at the top: all captures, with the columns Offers, Rejected and Result
    page.click("nav >> text=Captures")
    headers = page.locator("th").all_inner_texts()
    assert {"Offers", "Rejected", "Result"} <= set(headers)
    assert page.locator("tr:has(td)").count() == 2
    # 2. "Only failed captures": only the failed one, and its error is clear
    page.click("text=Only failed captures")
    assert page.locator("tr:has(td)").count() == 1
    page.click("td.capture-failed summary")
    assert REASON in page.locator("td.capture-failed").inner_text()
    shot(page, "377-failed")
    # 3. the same on the captures page of the trip
    page.goto(f"{base}/trips/{tid}")
    page.click(f'a[href="/trips/{tid}/captures"]')
    assert page.url.endswith(f"/trips/{tid}/captures")
    page.click("text=Only failed captures")
    assert page.locator("tr:has(td)").count() == 1
    # 4. "Reparse capture" with the real parser: after a reload the capture is not failed
    page.click("text=Reparse capture")
    page.wait_for_function("!document.body.innerText.includes('Reparse capture')")
    page.reload()
    assert "No failed captures." in page.inner_text("body")


def test_368_see_a_price_drop_mark_of_a_pinned_offer(live):
    page, base, auth, tid = live
    send(auth, tid, [offer("99.90", "ICE 105")])
    # 2. pin the offer, then open the trip page again
    page.goto(f"{base}/trips/{tid}")
    page.click("#table >> text=Pin")
    page.goto(f"{base}/trips/{tid}")
    assert "pinned" in page.inner_text("#table")
    # 3. the same offer with a lower price
    send(auth, tid, [offer("79.90", "ICE 105")])
    # 4. the trips list and the trip page show the drop
    page.goto(base + "/")
    assert "price dropped EUR 20.00" in page.inner_text("body")
    page.goto(f"{base}/trips/{tid}")
    assert "Price drops" in page.inner_text("body") and "price dropped EUR 20.00" in page.inner_text("body")
    shot(page, "368-drop")
    # 5. after the view, the box and the mark are gone
    page.goto(f"{base}/trips/{tid}")
    assert "Price drops" not in page.inner_text("body")
    page.goto(base + "/")
    assert "price dropped" not in page.inner_text("body")


def test_369_plan_a_round_trip(live):
    page, base, auth, out = live
    # 1. "Make the return trip": the form shows the places swapped; save it
    page.goto(f"{base}/trips/{out}")
    page.click("text=Make the return trip")
    assert page.input_value('input[name="origin_text"]') == "Zürich"
    assert page.input_value('input[name="destination_text"]') == "Amsterdam"
    ret = int(page.url.split("/trips/")[1].split("/")[0])
    page.click("text=Save")
    # 2. one capture into each trip
    send(auth, out, [offer("89.90", "ICE 105")])
    back = offer("40.00", "ICE 901")
    for leg in back["legs"]:
        leg["depart_at"] = "2026-12-27" + leg["depart_at"][10:]
        leg["arrive_at"] = "2026-12-27" + leg["arrive_at"][10:]
    send(auth, ret, [back])
    # 3. the trips list: the return trip directly under its outbound trip, with "Journey total"
    page.goto(base + "/")
    rows = page.locator("table tr").all_inner_texts()
    i = next(k for k, r in enumerate(rows) if r.startswith("Amsterdam – Zürich\t"))
    assert "(return)" in rows[i + 1] or "Return of" in rows[i + 1]
    assert "Journey total: EUR 129.90" in page.inner_text("body")
    shot(page, "369-list")
    # 4. the box "Journey" of each trip page: the link to the other direction, both offers, the total
    for this, other in ((out, ret), (ret, out)):
        page.goto(f"{base}/trips/{this}")
        box = page.locator("section.journey")
        assert box.locator(f'a[href="/trips/{other}"]').count() >= 1
        text = box.inner_text()
        assert "EUR 89.90" in text and "EUR 40.00" in text and "Total effective cost" in text
    shot(page, "369-journey")


def test_439_delete_a_test_trip(live):
    page, base, auth, _ = live
    api = TestClient(app)
    # 2. make the trip "delete test"
    page.goto(base + "/trips/new")
    page.fill('input[name="title"]', "delete test")
    page.click("text=Save")
    # 3. the trip list of the userscript (its dropdown reads GET /api/trips) has it
    assert "delete test" in [t["title"] for t in api.get("/api/trips", headers=auth).json()]
    # 4. the edit form, "Delete trip", the confirm page, "Delete"
    page.goto(base + "/")
    page.locator("tr", has_text="delete test").locator("text=Edit").click()
    tid = int(page.url.split("/trips/")[1].split("/")[0])
    page.click("text=Delete trip")
    assert page.url.endswith(f"/trips/{tid}/delete")
    page.click("button:has-text('Delete')")
    # 5. the trips list does not show it; 6. the userscript list does not have it
    page.goto(base + "/")
    assert "delete test" not in page.inner_text("body")
    shot(page, "439-list")
    assert "delete test" not in [t["title"] for t in api.get("/api/trips", headers=auth).json()]
    assert page.goto(f"{base}/trips/{tid}").status == 404
