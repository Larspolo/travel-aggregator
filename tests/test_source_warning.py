"""The warning of the trips list when the last captures of a source failed (#726)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip

PASSWORD = "pw"
T0 = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)
LINK = '/captures?failed=1&amp;source=bahn.de'


def _cap(trip_id, hours, ok):
    return Capture(trip_id=trip_id, source="bahn.de", parser_version="1.0.0", captured_at=T0 + timedelta(hours=hours),
                   offer_count=3 if ok else 0, rejected_count=0, unreadable=None if ok else "no JSON")


@pytest.fixture
def page(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})

    def seed(*oks, path="/"):
        with sessions() as s:
            trip = Trip(title="Reise")
            s.add(trip)
            s.flush()
            s.add_all([_cap(trip.id, i, ok) for i, ok in enumerate(oks)])
            s.commit()
        return c.get(path).text
    return seed


def test_three_failed_captures_show_the_warning(page):
    html = page(True, False, False, False)
    assert "bahn.de: the last 3 captures failed" in html
    assert LINK in html


def test_one_failed_capture_shows_no_warning(page):
    html = page(True, False)
    assert "source-warning" not in html


def test_a_good_capture_after_the_failed_ones_removes_the_warning(page):
    html = page(False, False, False, True)
    assert "source-warning" not in html


def test_the_archived_list_shows_the_warning(page):
    html = page(True, False, False, path="/?archived=1")
    assert "bahn.de: the last 2 captures failed" in html and LINK in html


@pytest.mark.slow
def test_the_warning_fits_the_phone_width(sessions, tmp_path):
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    from app.auth import require_login
    from tests.test_mobile_whole import _launch

    with sessions() as s:
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        s.add_all([_cap(trip.id, i, ok) for i, ok in enumerate((True, False, False, False))])
        s.add(Capture(trip_id=trip.id, source="a-very-long-source-name.example", parser_version="1.0.0",
                      captured_at=T0, offer_count=0, rejected_count=2, unreadable=None))
        s.add(Capture(trip_id=trip.id, source="a-very-long-source-name.example", parser_version="1.0.0",
                      captured_at=T0 + timedelta(hours=1), offer_count=0, rejected_count=2, unreadable=None))
        s.commit()
    app.dependency_overrides[require_login] = lambda: None
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            for width in (390, 1280):
                pg = browser.new_page(viewport={"width": width, "height": 800})
                pg.goto(f"http://127.0.0.1:{port}/")
                assert pg.locator(".source-warning .chip").count() == 2
                assert pg.evaluate("document.documentElement.scrollWidth") <= width
                pg.screenshot(path=str(tmp_path / f"warning-{width}.png"))
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
        app.dependency_overrides.pop(require_login, None)
