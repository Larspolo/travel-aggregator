"""The settings page shows the newest backup and a warning when it is old or missing (#548)."""

import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.backup import STAMP_FORMAT
from app.main import app

PASSWORD = "pw"
OLD = "The newest backup is older than 48 hours."
NONE = "No backup yet."


@pytest.fixture
def client(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _write(directory, when, size, label="daily"):
    directory.mkdir(exist_ok=True)
    (directory / f"{when.strftime(STAMP_FORMAT)}-{label}.dump").write_bytes(b"x" * size)


def test_recent_backup_shows_time_and_size(client, tmp_path):
    when = datetime.now(UTC) - timedelta(hours=1)
    _write(tmp_path / "bk", when - timedelta(days=5), 10)
    _write(tmp_path / "bk", when, 2048, "manual")
    (tmp_path / "bk" / "99999999T999999Z-x.dump").write_bytes(b"x")  # not a stamp
    (tmp_path / "bk" / "notes.txt").write_text("x")
    html = client.get("/settings").text
    assert when.strftime("%Y-%m-%d %H:%M") + " UTC" in html and "2048 bytes" in html
    assert OLD not in html and NONE not in html


def test_old_backup_shows_warning(client, tmp_path):
    _write(tmp_path / "bk", datetime.now(UTC) - timedelta(days=3), 5)
    assert OLD in client.get("/settings").text


def test_missing_and_empty_directory(client, tmp_path):
    r = client.get("/settings")
    assert r.status_code == 200 and NONE in r.text
    (tmp_path / "bk").mkdir()
    (tmp_path / "bk" / "other.dump").write_bytes(b"x")
    assert NONE in client.get("/settings").text


@pytest.mark.slow
def test_screenshots_and_no_scroll_at_390_px(client, tmp_path, monkeypatch):
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    _write(tmp_path / "bk", datetime.now(UTC) - timedelta(days=3), 5000)
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
                page = browser.new_page(viewport={"width": width, "height": 844})
                page.goto(f"http://127.0.0.1:{port}/login")
                page.fill("input[name=password]", PASSWORD)
                page.click("button[type=submit]")
                page.goto(f"http://127.0.0.1:{port}/settings")
                assert page.get_by_text(OLD).is_visible()
                page.screenshot(path=os.path.join(shots, f"settings-backups-{width}.png"), full_page=True)
                if width == 390:
                    assert page.evaluate("document.documentElement.scrollWidth") <= 390
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
