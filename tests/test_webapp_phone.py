"""Each page links the web app manifest and the touch icon, and Chromium reads the manifest on a phone (#826).

The home-screen feature of epic #795: the unit tests check the HTML and the JSON; this test loads the pages in a
phone browser and checks the links and the manifest that Chromium reads.
"""

import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

PAGES = [("trips", "/"), ("archive", "/?archived=1"), ("trip-new", "/trips/new"), ("source-new", "/sources/new"),
         ("captures", "/captures"), ("profiles", "/profiles"), ("places", "/places"), ("settings", "/settings"), ("messages", "/settings/messages"),
         ("rates", "/rates"), ("tokens", "/tokens"), ("login", "/login")]


def _serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server, thread, f"http://127.0.0.1:{port}"


def _launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


def _problems(p, browser, base, path):
    """Give the problems of one page on a phone: a missing link, or a manifest that Chromium reads with errors."""
    found = []
    ctx = browser.new_context(**p.devices["iPhone 13"])
    try:
        page = ctx.new_page()
        response = page.goto(base + path)
        if response.status >= 400:
            return [f"status {response.status}"]
        manifest = page.locator('link[rel="manifest"]')
        if manifest.count() != 1 or manifest.get_attribute("href") != "/manifest.webmanifest":
            found.append("manifest link missing or wrong")
        if page.locator('link[rel="apple-touch-icon"]').count() != 1:
            found.append("apple-touch-icon link missing")
        result = ctx.new_cdp_session(page).send("Page.getAppManifest")
        if result["errors"]:
            found.append(f"manifest errors: {result['errors']}")
        if not result.get("data"):
            found.append("manifest is empty")
    finally:
        ctx.close()
    return found


def test_all_pages_link_the_manifest_and_the_touch_icon_on_a_phone(trip, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90", "ICE 105")])
    pages = PAGES + [("trip", f"/trips/{tid}"), ("trip-edit", f"/trips/{tid}/edit")]
    server, thread, base = _serve()
    found = {}
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            for _name, path in pages:
                bad = _problems(p, browser, base, path)
                if bad:
                    found[path] = bad
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
    assert found == {}, "\n".join(f"{k}: {v}" for k, vs in found.items() for v in vs)
