"""p pins and h hides the focused row of the trip page; the focus follows the row after the swap (#2438)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Trip
from tests.test_a11y_browser import launch
from tests.test_trip_alternatives_browser import ROWS, _offer, server  # noqa: F401
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow

ACTIVE = "document.activeElement.id"


def test_p_pins_and_h_hides_the_focused_row(server, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, token = server
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    ingest(TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id,
           [_offer(f"ICE {n}", "Zürich HB", f"{80 + n}.00") for n in range(4)])
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{base}/trips/{trip_id}")
        page.wait_for_selector(ROWS)
        ids = page.eval_on_selector_all('tr[id^="it-"]', "rs => rs.map(r => r.id)")
        page.focus("input[name=hour_markup]")
        page.keyboard.press("p")
        page.wait_for_timeout(300)
        assert "pinned" not in page.inner_text("#rows")
        page.evaluate("document.activeElement.blur()")
        page.keyboard.press("j")
        page.keyboard.press("j")
        page.keyboard.press("p")
        pinned = f"document.getElementById('{ids[1]}').innerText.includes('pinned')"
        page.wait_for_function(f"{pinned} && document.activeElement.id === '{ids[1]}'")
        page.keyboard.press("p")
        page.wait_for_function(f"!{pinned} && document.activeElement.id === '{ids[1]}'")
        page.keyboard.press("h")
        page.wait_for_function(f"!document.getElementById('{ids[1]}') && document.activeElement.id === '{ids[2]}'")
        assert page.evaluate(ACTIVE) == ids[2]
        browser.close()
