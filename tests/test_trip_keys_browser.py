"""j and k move the focus between the rows of the trip page, Enter opens or closes the details (#2437)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Trip
from tests.test_a11y_browser import launch
from tests.test_trip_alternatives_browser import ROWS, _offer, server  # noqa: F401
from tests.test_trip_page import ingest

pytestmark = pytest.mark.slow

ACTIVE = "document.activeElement.id"


def test_j_k_and_enter_on_the_rows(server, sessions):  # noqa: F811
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
        assert len(ids) == 4
        page.keyboard.press("j")
        page.keyboard.press("j")
        assert page.evaluate(ACTIVE) == ids[1]
        assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
        page.keyboard.press("k")
        assert page.evaluate(ACTIVE) == ids[0]
        opened = f"document.getElementById('{ids[0]}').nextElementSibling.querySelector('details').open"
        page.keyboard.press("Enter")
        assert page.evaluate(opened) is True
        page.keyboard.press("Enter")
        assert page.evaluate(opened) is False
        page.keyboard.press("Control+j")
        assert page.evaluate(ACTIVE) == ids[0]
        page.focus("input[name=hour_markup]")
        page.keyboard.press("j")
        assert page.evaluate("document.activeElement.name") == "hour_markup"
        browser.close()
