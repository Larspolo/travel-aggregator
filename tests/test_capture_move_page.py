"""The captures pages have "Move to trip" for each capture with raw data (#580, epic #578)."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"


def _csrf(c, path):
    groups = re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)
    return next(t for t in groups if t)


def _setup(sessions, monkeypatch, raw=True):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        wrong = Trip(title="Wrong <trip>", origin_text="Lisboa", destination_text="Porto")
        right = Trip(title="Köln & München", origin_text="Köln", destination_text="München")
        s.add_all([wrong, right])
        s.commit()
        ids = wrong.id, right.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    body = {"trip_id": ids[0], "source": "bahn.de", "parser_version": "0.0.1", "captured_at": "2026-11-03T19:41:00Z",
            "raw": json.loads(FIX.read_text())}
    r = c.post("/api/ingest", headers={"Authorization": f"Bearer {token}"}, json=body)
    assert r.status_code < 300, r.text
    with sessions() as s:
        capture = s.scalars(select(Capture)).one()
        if not raw:
            capture.raw_gz = None
            s.commit()
        cid = capture.id
    return c, ids, cid


def _move(c, cid, trip_id, path="/captures"):
    return c.post(f"/captures/{cid}/move", data={"trip_id": trip_id}, headers={"X-CSRF-Token": _csrf(c, path)})


def test_a_capture_with_raw_has_the_trip_list_and_the_button(sessions, monkeypatch):
    c, (wrong, right), cid = _setup(sessions, monkeypatch)
    for path in ("/captures", f"/trips/{wrong}/captures"):
        html = c.get(path).text
        assert "Move to trip" in html
        assert f'<option value="{right}">' in html
        assert f'<option value="{wrong}">' not in html


def test_a_capture_with_no_raw_has_no_button(sessions, monkeypatch):
    c, (wrong, _), _ = _setup(sessions, monkeypatch, raw=False)
    assert "Move to trip" not in c.get(f"/trips/{wrong}/captures").text


def test_a_move_answers_with_the_counts_and_moves_the_capture(sessions, monkeypatch):
    c, (wrong, right), cid = _setup(sessions, monkeypatch)
    r = _move(c, cid, right)
    assert r.status_code == 200
    assert re.search(r"Moved to Köln &amp; München: \d+ created, \d+ updated, \d+ unchanged, \d+ rejected\.", r.text)
    assert f"/captures/{cid}/move" in c.get(f"/trips/{right}/captures").text
    assert f"/captures/{cid}/move" not in c.get(f"/trips/{wrong}/captures").text


def test_no_csrf_token_gives_403(sessions, monkeypatch):
    c, (_, right), cid = _setup(sessions, monkeypatch)
    assert c.post(f"/captures/{cid}/move", data={"trip_id": right}).status_code == 403


def test_a_capture_that_does_not_exist_gives_404(sessions, monkeypatch):
    c, (_, right), cid = _setup(sessions, monkeypatch)
    assert _move(c, cid + 999, right).status_code == 404


def test_the_same_trip_or_no_trip_gives_a_message_and_no_change(sessions, monkeypatch):
    c, (wrong, right), cid = _setup(sessions, monkeypatch)
    assert "already in this trip" in _move(c, cid, wrong).text
    assert f"no trip {right + 999}" in _move(c, cid, right + 999).text
    with sessions() as s:
        assert s.get(Capture, cid).trip_id == wrong


@pytest.mark.slow
def test_screenshots_and_no_scroll_at_390_px(sessions, monkeypatch, tmp_path):
    import os
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    _, (wrong, right), cid = _setup(sessions, monkeypatch)
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
                page.goto(f"http://127.0.0.1:{port}/trips/{wrong}/captures")
                assert page.get_by_role("button", name="Move to trip").is_visible()
                page.screenshot(path=os.path.join(shots, f"capture-move-{width}.png"), full_page=True)
                if width == 390:
                    assert page.evaluate("document.documentElement.scrollWidth") <= 390
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
