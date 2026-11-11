"""The mark "no later connection captured" at a transfer of a row (#1774), also with a penalty of €0."""

import copy
import os
import socket
import threading
import time

import pytest
import uvicorn

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

MARK = "no later connection captured"


def _later_from_basel():
    o = copy.deepcopy(offer("40.00", "IC 63", "SBB"))
    o["legs"] = [dict(o["legs"][1], service_no="IC 63",
                      depart_at="2026-12-20T15:33:00+01:00", arrive_at="2026-12-20T16:26:00+01:00")]
    return o


def test_a_transfer_with_no_later_connection_has_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    assert f"Transfer at Basel SBB: 0h 31 · {MARK}" in client.get(f"/trips/{trip_id}").text


def test_a_later_connection_removes_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), _later_from_basel()])
    page = client.get(f"/trips/{trip_id}").text
    assert "Transfer at Basel SBB: 0h 31<" in page and MARK not in page


@pytest.mark.slow
def test_the_mark_is_text_and_the_row_fits_a_phone(trip):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    exe = "/opt/pw-browsers/chromium"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if os.path.exists(exe) \
                else p.chromium.launch()
            for name, ctx in (("1280", {"viewport": {"width": 1280, "height": 900}}),
                              ("390", dict(p.devices["iPhone 12"]))):
                context = browser.new_context(**ctx)
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{port}/trips/{trip_id}")
                page.locator("tr.detail summary").first.click()
                transfer = page.locator("tr.detail .transfer").first
                assert MARK in transfer.inner_text()
                width = page.evaluate("window.innerWidth")
                assert page.evaluate("document.documentElement.scrollWidth") <= width, name
                if os.environ.get("SHOTS"):  # the screenshots of the PR
                    page.screenshot(path=os.path.join(os.environ["SHOTS"], f"fallback-mark-{name}.png"), full_page=True)
                context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
