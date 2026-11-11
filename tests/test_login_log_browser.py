"""The card "Recent logins" with 20 rows and a long User-Agent fits at 390 px and passes axe (#1355)."""

import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from sqlalchemy.orm import Session

from app.auth import require_login
from app.main import app
from app.models import LoginEvent
from tests.test_a11y_browser import launch, serious

pytestmark = pytest.mark.slow

LONG_AGENT = "a" * 300  # no space: the text can only break inside the word
ADDRESS = "2001:db8:85a3:0:0:8a2e:370:7334"


@pytest.fixture
def server(sessions, tmp_path, monkeypatch):
    """The live server with 20 login rows; the login is not checked here."""
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    with Session(sessions.kw["bind"]) as s:
        now = datetime.now(UTC)
        for i in range(20):
            s.add(LoginEvent(at=now - timedelta(minutes=i), address=ADDRESS,
                             user_agent=LONG_AGENT if i == 0 else "Mozilla/5.0 (Linux; Android 14) Firefox/121.0",
                             result="failed" if i % 3 == 0 else "ok"))
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
def test_the_login_card_fits_and_passes_axe(server, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(f"{server}/settings")
        rows = page.locator(".login-log li")
        assert rows.count() == 20
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert serious(page) == set()
        browser.close()
