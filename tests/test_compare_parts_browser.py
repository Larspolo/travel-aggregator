"""The part rows of the compare view fit at 1280 px and 390 px and scroll with the keyboard (#2088)."""

import socket
import threading
import time
from urllib.parse import urlencode

import pytest
import uvicorn
from sqlalchemy import select

from app.models import Itinerary
from tests.test_compare_parts_whole import PARAMS, setup
from tests.test_mobile_controls import _launch
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

pytestmark = pytest.mark.slow


@pytest.fixture
def compare_url(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids = setup(client, auth, trip_id, sessions)
    ingest(client, auth, trip_id, [direct("150.00")])
    with sessions() as s:
        ids.append(next(i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))
                        if i.legs[0].service_no == "ICE 9"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/trips/{trip_id}/compare?" + urlencode({**PARAMS, "it": ids}, doseq=True)
    server.should_exit = True
    thread.join(5)


ROWS_SHOWN = """() => {
    const box = document.querySelector('div.scroll');
    const rows = [...box.querySelectorAll('tr')];
    const b = box.getBoundingClientRect();
    return rows.filter(tr => {
        const cells = [...tr.children];
        return !cells.every(c => {
            c.scrollIntoView({block: 'nearest', inline: 'nearest'});
            const r = c.getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return r.left >= b.left - 1 && r.right <= b.right + 1 && r.width > 0 && r.height > 0
                && hit !== null && c.contains(hit);
        });
    }).map(tr => tr.firstElementChild.textContent);
}"""


@pytest.mark.parametrize("width", [1280, 390])
def test_the_part_rows_fit_and_the_box_scrolls_with_the_keys(compare_url, width):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": width, "height": 800})
        assert page.goto(compare_url).status == 200
        assert page.locator("table.compare tr:first-child td").count() == 4
        for label in ("access time", "night travel", "short transfer"):
            assert page.locator(f'table.compare th[scope=row]:text-is("{label}")').count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.evaluate(ROWS_SHOWN) == []  # each cell is visible after a scroll of the box
        page.evaluate("() => { document.querySelector('div.scroll').scrollLeft = 0; scrollTo(0, 0); }")
        box = page.locator("div.scroll")
        for _ in range(30):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement === document.querySelector('div.scroll')"):
                break
        assert page.evaluate("document.activeElement === document.querySelector('div.scroll')")
        end = page.evaluate("(b => b.scrollWidth - b.clientWidth)(document.querySelector('div.scroll'))")
        if width == 390:
            assert end > 0  # 4 columns do not fit on a phone
        for _ in range(60):
            page.keyboard.press("ArrowRight")
        page.wait_for_function(f"document.querySelector('div.scroll').scrollLeft >= {end} - 1")
        last = page.locator("table.compare tr:first-child td").last.bounding_box()
        b = box.bounding_box()
        assert last["x"] + last["width"] <= b["x"] + b["width"] + 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
