"""The best effective cost line in the price trend chart of the trip page (#2141)."""

import os
import re
import socket
import threading
import time
from datetime import date
from decimal import Decimal

import pytest
import uvicorn

from app.history import trend_chart
from tests.test_history_whole import capture, trip  # noqa: F401  (trip is a fixture)

DAYS = (("89.90", "03"), ("85.00", "04"), ("95.00", "05"))


def _titles(page, name):
    group = page.split(f"<title>{name}</title>", 1)[1].split("</g>", 1)[0]
    return re.findall(r"<title>([^<]+)</title>", group)


def test_two_lists_give_two_lines_on_one_scale():
    c = trend_chart([(date(2026, 12, 1), Decimal("100.00")), (date(2026, 12, 2), Decimal("120.00"))],
                    scores=[(date(2026, 12, 1), Decimal("150.00")), (date(2026, 12, 2), Decimal("140.00"))])
    first, second = c["lines"]
    assert first["name"] == "Cheapest price per day" and second["name"] == "Best effective cost per day"
    assert c["low"] == Decimal("100.00") and c["high"] == Decimal("150.00")
    assert second["dots"][0]["title"] == "2026-12-01: €150.00"
    assert second["dots"][0]["y"] < second["dots"][1]["y"] < first["dots"][1]["y"] < first["dots"][0]["y"]
    assert len(trend_chart([(date(2026, 12, 1), Decimal("1"))])["lines"]) == 1


def test_the_trip_page_shows_both_lines(trip):  # noqa: F811
    client, auth, trip_id = trip
    for price, day in DAYS:
        capture(client, auth, trip_id, price, f"2026-11-{day}T10:00:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert "Cheapest price per day" in page and "Best effective cost per day" in page
    scores = _titles(page, "Best effective cost per day")
    assert [t[:10] for t in scores] == ["2026-11-03", "2026-11-04", "2026-11-05"]
    assert all("€" in t for t in scores)


def test_the_hour_value_changes_only_the_second_line(trip):  # noqa: F811
    client, auth, trip_id = trip
    for price, day in DAYS:
        capture(client, auth, trip_id, price, f"2026-11-{day}T10:00:00Z")
    base = client.get(f"/trips/{trip_id}").text
    more = client.get(f"/trips/{trip_id}?hour_markup=30").text
    assert _titles(base, "Cheapest price per day") == _titles(more, "Cheapest price per day")
    assert _titles(base, "Best effective cost per day") != _titles(more, "Best effective cost per day")


@pytest.mark.slow
def test_both_lines_and_the_legend_fit(trip):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, trip_id = trip
    for price, day in DAYS:
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
            for name, kwargs in (("phone", p.devices["iPhone 13"]),
                                 ("desktop", {"viewport": {"width": 1280, "height": 900}})):
                page = browser.new_context(**kwargs).new_page()
                page.goto(f"http://127.0.0.1:{port}/trips/{trip_id}")
                assert page.locator("#trend polyline").count() == 2
                assert page.locator("#trend .trend-legend li").count() == 2
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
                if shots:
                    page.locator("#trend").screenshot(path=f"{shots}/trend-score-{name}.png")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
