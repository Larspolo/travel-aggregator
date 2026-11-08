"""The settings page shows the card "Storage" (#1236)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.storage import human_bytes

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _captures(sessions):
    with sessions() as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        now = datetime.now(UTC)
        for source, size, age in (("bahn", 100, 1), ("bahn", 200, 400), ("flixbus", 50, 1)):
            s.add(Capture(trip_id=trip.id, source=source, captured_at=now - timedelta(days=age), raw_gz=b"x" * size))
        s.commit()


def test_card_line_and_rows(client, sessions):
    _captures(sessions)
    html = client.get("/settings").text
    assert "Storage" in html
    assert "raw captures 350 B in 3 captures" in html
    assert "the next cleanup removes 1 captures (200 B)" in html
    assert html.count('class="storage-row"') == 2


def test_zero_keeps_all(client, sessions):
    _captures(sessions)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/settings").text).group(1)
    r = client.post("/settings", data={"retention": "0", "csrf_token": token}, follow_redirects=True)
    assert r.status_code == 200
    assert "the cleanup removes nothing" in client.get("/settings").text


def test_human_bytes():
    assert [human_bytes(n) for n in (0, 512, 1536, 92274688, 1288490189)] == ["0 B", "512 B", "1.5 KB", "88 MB", "1.2 GB"]


@pytest.mark.slow
def test_screenshots_and_no_scroll_at_390_px(client, sessions, tmp_path):
    import os
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    _captures(sessions)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for width in (1280, 390):
                page = browser.new_page(viewport={"width": width, "height": 844}, device_scale_factor=2)
                page.goto(f"http://127.0.0.1:{port}/login")
                page.fill("input[name=password]", PASSWORD)
                page.click("button[type=submit]")
                page.goto(f"http://127.0.0.1:{port}/settings")
                assert page.locator(".storage-line").is_visible()
                page.screenshot(path=os.path.join(shots, f"settings-storage-{width}.png"), full_page=True)
                if width == 390:
                    assert page.evaluate("document.documentElement.scrollWidth") <= 390
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
