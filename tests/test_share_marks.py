"""The "Suits me" marks of the travel partner on the read-only link of a trip (#1781, epic #1780)."""

import os
import re
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import token_limiter
from app.main import app
from app.models import Itinerary, ShareMark, Trip
from tests.test_share import _csrf, _setup, share
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _rows(sessions, trip_id):
    with sessions() as s:
        return {i.legs[0].service_no: i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}


def _marks(sessions, trip_id):
    with sessions() as s:
        return {m.itinerary_id for m in s.scalars(select(ShareMark).where(ShareMark.trip_id == trip_id))}


def _marked_rows(page):
    return set(map(int, re.findall(r'<li class="card shared-row marked" id="row-(\d+)"', page)))


def test_a_click_marks_a_row_and_a_second_click_removes_the_mark(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)  # the travel partner: no login, no CSRF token
    page = anon.get(link).text
    assert page.count("Suits me</button>") == 2 and not _marked_rows(page)

    r = anon.post(f"{link}/marks/{rows['ICE 105']}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{link}#row-{rows['ICE 105']}"
    assert r.headers["cache-control"] == "no-store"
    assert _marks(sessions, trip_id) == {rows["ICE 105"]}
    page = anon.get(link).text
    assert _marked_rows(page) == {rows["ICE 105"]}
    assert page.count("Suits you") == 1 and page.count("Suits me</button>") == 1

    anon.post(f"{link}/marks/{rows['ICE 123']}")
    assert _marks(sessions, trip_id) == {rows["ICE 105"], rows["ICE 123"]}
    assert anon.post(f"{link}/marks/{rows['ICE 105']}").status_code == 200  # the redirect to the page
    assert _marks(sessions, trip_id) == {rows["ICE 123"]}
    assert _marked_rows(anon.get(link).text) == {rows["ICE 123"]}


def test_a_bad_token_or_a_row_that_the_page_does_not_show_gives_404(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app, client=("198.51.100.23", 50000))
    token_limiter.reset()
    try:
        assert anon.post(f"/s/unknown/marks/{rows['ICE 105']}").status_code == 404
        assert token_limiter.retry_after("198.51.100.23") == 0  # a failure counts, no lock yet
        for _ in range(token_limiter.ADDRESS_MAX - 1):
            anon.post(f"/s/unknown/marks/{rows['ICE 105']}")
        assert anon.post(f"{link}/marks/{rows['ICE 105']}").status_code == 429  # the address is locked (#904)
    finally:
        token_limiter.reset()
    assert anon.post(f"{link}/marks/{rows['ICE 999']}").status_code == 404  # the hidden row
    assert anon.post(f"{link}/marks/999999").status_code == 404
    assert anon.post(f"{link}/marks/abc").status_code == 422
    assert _marks(sessions, trip_id) == set()


def test_a_row_of_another_trip_gives_404(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    with sessions() as s:
        other = Trip(title="Other trip")
        s.add(other)
        s.commit()
        other_id = other.id
    link = share(client, other_id)
    rows = _rows(sessions, trip_id)
    assert TestClient(app).post(f"{link}/marks/{rows['ICE 105']}").status_code == 404
    assert _marks(sessions, trip_id) == set() and _marks(sessions, other_id) == set()


def test_revoke_and_a_new_link_delete_the_marks_and_stop_the_old_mark_requests(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    anon = TestClient(app)
    first = share(client, trip_id)
    anon.post(f"{first}/marks/{rows['ICE 105']}")
    assert _marks(sessions, trip_id) == {rows["ICE 105"]}
    second = share(client, trip_id)  # a new link starts with no marks
    assert _marks(sessions, trip_id) == set()
    assert anon.post(f"{first}/marks/{rows['ICE 105']}").status_code == 404
    anon.post(f"{second}/marks/{rows['ICE 123']}")
    assert _marks(sessions, trip_id) == {rows["ICE 123"]}
    client.post(f"/trips/{trip_id}/share/revoke", data={"csrf_token": _csrf(client, trip_id)})
    assert _marks(sessions, trip_id) == set()
    assert anon.get(second).status_code == 404
    assert anon.post(f"{second}/marks/{rows['ICE 123']}").status_code == 404
    assert _marks(sessions, trip_id) == set()


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0040")
    engine = create_engine(empty_database_url)
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("share_marks")}
        assert cols == {"id", "trip_id", "itinerary_id", "note", "created_at"}
        command.downgrade(cfg, "0039")
        assert "share_marks" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


@pytest.mark.slow
def test_the_partner_marks_a_row_in_a_browser_at_phone_and_desktop_width(trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    out = os.environ.get("SCREENSHOT_DIR")
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for width, row in ((390, "ICE 105"), (1280, "ICE 123")):
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2,
                                        has_touch=width < 500)
                page.goto(f"http://127.0.0.1:{port}{link}")
                button = page.locator(f"#row-{rows[row]} button")
                button.tap() if width < 500 else button.click()
                page.wait_for_selector(f"#row-{rows[row]}.marked")
                assert page.locator(f"#row-{rows[row]} .suits").inner_text().strip() == "Suits you"
                assert page.evaluate("document.documentElement.scrollWidth") <= width
                if out:
                    page.screenshot(path=f"{out}/shared-marked-{width}.png", full_page=True)
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
    assert _marks(sessions, trip_id) == {rows["ICE 105"], rows["ICE 123"]}
