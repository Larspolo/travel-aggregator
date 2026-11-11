"""The price trend chart of a trip on the trip page (#851): one point per day, shown only for 2 or more days."""

import os
import socket
import threading
import time
from datetime import date
from decimal import Decimal

import pytest
import uvicorn

from app.history import trend_chart
from tests.test_history_whole import capture, trip  # noqa: F401  (trip is a fixture)


def test_three_days_give_three_points_with_titles():
    c = trend_chart([(date(2026, 12, 1), Decimal("85.00")), (date(2026, 12, 2), Decimal("90.00")),
                     (date(2026, 12, 3), Decimal("80.00"))])
    dots = c["lines"][0]["dots"]
    assert [d["title"] for d in dots] == ["2026-12-01: €85.00", "2026-12-02: €90.00", "2026-12-03: €80.00"]
    assert c["low"] == Decimal("80.00") and c["high"] == Decimal("90.00")
    assert dots[0]["x"] < dots[1]["x"] < dots[2]["x"] and dots[1]["y"] < dots[0]["y"] < dots[2]["y"]


def test_a_trip_with_captures_on_three_days_shows_the_chart(trip):  # noqa: F811
    client, auth, trip_id = trip
    for price, day in (("89.90", "03"), ("85.00", "04"), ("95.00", "05")):
        capture(client, auth, trip_id, price, f"2026-11-{day}T10:00:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert "<h2>Price trend</h2>" in page
    assert page.count("<circle") >= 3
    for title in ("2026-11-03: €89.90", "2026-11-04: €85.00", "2026-11-05: €95.00"):
        assert f"<title>{title}</title>" in page
    assert "low €85.00" in page and "high €" in page  # high: of both lines, one scale (#2141)


def test_one_day_or_no_capture_shows_no_chart(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert "Price trend" not in client.get(f"/trips/{trip_id}").text
    capture(client, auth, trip_id, "89.90", "2026-11-03T08:00:00Z")
    capture(client, auth, trip_id, "80.00", "2026-11-03T18:00:00Z")
    assert "Price trend" not in client.get(f"/trips/{trip_id}").text


@pytest.mark.slow
def test_the_chart_fits_a_phone(trip):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    for price, day in (("89.90", "03"), ("85.00", "04"), ("95.00", "05")):
        capture(client, auth, trip_id, price, f"2026-11-{day}T10:00:00Z")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    exe = "/opt/pw-browsers/chromium"
    shots = os.environ.get("TREND_SHOTS")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for name, kwargs in (("phone", p.devices["iPhone 13"]), ("desktop", {"viewport": {"width": 1280, "height": 900}})):
                page = browser.new_context(**kwargs).new_page()
                page.goto(f"http://127.0.0.1:{port}/trips/{trip_id}")
                chart = page.locator("#trend svg.price-chart")
                assert chart.count() == 1 and chart.bounding_box()["width"] > 0
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
                if shots:
                    page.locator("#trend").screenshot(path=f"{shots}/trend-{name}.png")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
