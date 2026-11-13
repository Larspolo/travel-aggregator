"""The transfer line with platforms ("platform 4 → 5") wraps at 390 px, and the expanded row has no sideways scroll
(#2754, epic #2739). The Köln → München capture is the bahn.de fixture; the browser runs the trip page at 390 px."""

import json
import socket
import threading
import time
from datetime import date
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.browser_wait import wait_js
from tests.test_a11y_browser import launch

pytestmark = pytest.mark.slow

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"
ROWS = "#rows > tr:not(.detail)"


@pytest.fixture
def live(sessions):
    with sessions() as s:
        token = tokens.create(s, "test-platforms")
        t = Trip(title="Köln – München", origin_text="Köln", destination_text="München",
                 date_from=date(2026, 11, 6), date_to=date(2026, 11, 6))
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    body = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0",
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = TestClient(app).post("/api/ingest", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/trips/{trip_id}"
    server.should_exit = True
    thread.join(5)
    app.dependency_overrides.pop(require_login, None)


def test_the_platform_transfer_line_wraps_and_the_row_has_no_sideways_scroll_at_390(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live)
        page.wait_for_selector(ROWS)
        detail = page.locator("tr.detail", has_text="platform 4 → 5").first
        detail.locator("summary", has_text="Legs and fares").click()
        wait_js(page, "document.querySelector('tr.detail details[open]') !== null")
        line = detail.locator(".transfer", has_text="platform 4 → 5")
        line.scroll_into_view_if_needed()
        box = line.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, box
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()
