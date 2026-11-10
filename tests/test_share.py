"""The read-only page of a trip at a secret link (#903)."""

import os
import re
import socket
import threading
import time

import pytest
import uvicorn

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def share(client, trip_id) -> str:
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": _csrf(client, trip_id)})
    assert r.status_code == 200
    link = re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1)
    assert "Revoke link" in r.text
    return link.removeprefix("http://testserver")


def _setup(client, auth, trip_id, sessions):
    ingest(client, auth, trip_id, [offer("119.90", "ICE 123"), offer("89.90", "ICE 105"), offer("50.00", "ICE 999")])
    with sessions() as s:
        its = {i.legs[0].service_no: i for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}
        its["ICE 999"].hidden = True
        its["ICE 105"].note = "secret-note-text"
        s.get(Trip, trip_id).notes = "secret-trip-notes"
        s.commit()


def test_a_shared_link_shows_the_ranked_rows_with_no_login_and_no_private_data(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    link = share(client, trip_id)
    assert link.startswith("/s/")
    r = TestClient(app).get(link)
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    page = r.text
    assert page.index("€89.90") < page.index("€119.90")
    assert "€50.00" not in page  # the hidden row
    for private in ("secret-note-text", "secret-trip-notes", "bahn.de/buchung", "captures", "Log out"):
        assert private not in page
    # the only forms are the "Suits me" marks of the rows (#1781): no form of the owner
    assert re.findall(r'<form [^>]*action="([^"]+)"', page) == [f"{link}/marks/{i}" for i in
                                                               re.findall(r'id="row-(\d+)"', page)]
    assert page.count("<form") == 2


def test_revoke_and_a_new_share_stop_the_old_link(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    anon = TestClient(app)
    first = share(client, trip_id)
    r = client.post(f"/trips/{trip_id}/share/revoke", data={"csrf_token": _csrf(client, trip_id)})
    assert r.status_code == 200 and ">Share<" in r.text.replace("</svg>", ">")
    assert anon.get(first).status_code == 404
    second = share(client, trip_id)
    third = share(client, trip_id)
    assert anon.get(first).status_code == 404 and anon.get(second).status_code == 404
    assert anon.get(third).status_code == 200
    assert anon.get("/s/unknown").status_code == 404


def test_share_needs_the_csrf_token(trip):  # noqa: F811
    client, _, trip_id = trip
    assert client.post(f"/trips/{trip_id}/share").status_code == 403


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0020")
    engine = create_engine(empty_database_url)
    try:
        assert {"share_hash", "shared_at"} <= {c["name"] for c in inspect(engine).get_columns("trips")}
        command.downgrade(cfg, "0019")
        assert not {"share_hash", "shared_at"} & {c["name"] for c in inspect(engine).get_columns("trips")}
    finally:
        engine.dispose()


@pytest.mark.slow
def test_screenshots_of_the_shared_page(trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
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
            for width in (1280, 390):
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
                page.goto(f"http://127.0.0.1:{port}{link}")
                assert page.locator("li.shared-row").count() == 2
                assert page.evaluate("document.documentElement.scrollWidth") <= width
                if out:
                    page.screenshot(path=f"{out}/shared-{width}.png", full_page=True)
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
