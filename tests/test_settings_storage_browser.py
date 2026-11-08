"""The card "Storage" with 3 sources and a long source name fits at 1280 px and 390 px and passes axe (#1237)."""

import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from sqlalchemy.orm import Session

from app.auth import require_login
from app.main import app
from app.models import Capture, Trip
from tests.test_a11y_browser import launch, serious

pytestmark = pytest.mark.slow

LONG = "a-very-long-source-name-of-forty-chars-x"
assert len(LONG) == 40


@pytest.fixture
def server(sessions, tmp_path, monkeypatch):
    """The live server with captures of 3 sources; the login is not checked here."""
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    with Session(sessions.kw["bind"]) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        now = datetime.now(UTC)
        for source, size in (("bahn", 3000), (LONG, 2000), ("flixbus", 1000)):
            s.add(Capture(trip_id=trip.id, source=source, captured_at=now - timedelta(days=1), raw_gz=b"x" * size))
        s.commit()
    app.dependency_overrides[require_login] = lambda: None
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)
    app.dependency_overrides.pop(require_login, None)


@pytest.mark.parametrize("width", [1280, 390])
def test_the_storage_card_fits(server, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(f"{server}/settings")
        line = page.locator(".storage-line").inner_text()
        assert "raw captures 5.9 KB in 3 captures" in line
        rows = page.locator(".storage-row")
        assert rows.count() == 3
        assert [rows.nth(i).locator("td").first.inner_text() for i in range(3)] == ["bahn", LONG, "flixbus"]
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert serious(page) == set()
        browser.close()
