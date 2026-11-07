"""The price chart uses the colors of the page, in light and dark mode (#698).

Before the fix the dots and the low/high labels were SVG black: unreadable on the dark page.
"""

from datetime import timedelta

import pytest

from app.models import Itinerary
from tests.test_all_pages_look import _launch, _serve
from tests.test_demo_screenshots import BAHN, _capture
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_price_chart_dots_and_labels_are_not_black(trip, sessions, scheme):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    # two captures of the same offers, so that the chart has a line with dots
    for age in (timedelta(hours=2), timedelta(hours=1)):
        r = client.post("/api/ingest", json={"trip_id": tid, **_capture("bahn.de", BAHN, age)}, headers=auth)
        assert r.status_code == 200, r.text
    with sessions() as s:
        it = s.query(Itinerary).filter_by(trip_id=tid).order_by(Itinerary.id).first().id
    server, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": 1280, "height": 800}, color_scheme=scheme)
            assert page.goto(f"{base}/trips/{tid}/itineraries/{it}/history").status < 400
            assert page.locator("svg.price-chart circle").count() > 0
            assert page.locator("svg.price-chart text").count() == 2
            fills = page.evaluate("""() => [
                ...[...document.querySelectorAll('.price-chart circle')].map(e => getComputedStyle(e).fill),
                ...[...document.querySelectorAll('.price-chart text')].map(e => getComputedStyle(e).fill)]""")
            assert "rgb(0, 0, 0)" not in fills, fills
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
