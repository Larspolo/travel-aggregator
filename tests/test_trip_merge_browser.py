"""The merge of two trips in the browser, at 1280 and 390 px: the edit page, the confirmation page, the target
trip page and the trips list (#1263)."""

import pytest
from sqlalchemy import select

from app.models import Itinerary, Trip
from tests.test_a11y_browser import launch, serious
from tests.test_mobile_width import live  # noqa: F401  (fixture: the live server, trip A with 20 itineraries)
from tests.test_trip_page import trip  # noqa: F401  (fixture)

pytestmark = pytest.mark.slow

ONLY_SOURCE = "only-in-the-source"


@pytest.mark.parametrize("width", [1280, 390])
def test_the_merge_flow_works_and_has_no_axe_finding(live, sessions, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, target_id, _ = live
    with sessions() as s:
        target_it = s.scalars(select(Itinerary).where(Itinerary.trip_id == target_id).order_by(Itinerary.id)).first()
        fp = target_it.fingerprint
        times = {k: getattr(target_it, k) for k in ("depart_at", "arrive_at", "duration_min", "first_seen_at", "last_seen_at")}
        source = Trip(title="Amsterdam → Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(source)
        s.flush()
        # one journey that both trips have (the same fingerprint, pinned here), and one only in the source
        s.add(Itinerary(trip_id=source.id, fingerprint=fp, pinned=True, **times))
        s.add(Itinerary(trip_id=source.id, fingerprint=ONLY_SOURCE, **times))
        s.commit()
        source_id = source.id
        before = s.query(Itinerary).filter_by(trip_id=target_id).count()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(f"{base}/trips/{source_id}/edit")
        page.wait_for_load_state("networkidle")
        page.select_option("#f-merge-into", str(target_id))
        page.get_by_role("button", name="Merge…").click()
        page.wait_for_url(f"**/trips/{source_id}/merge?into={target_id}")
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert serious(page) == set()
        page.get_by_role("button", name="Merge", exact=True).click()
        page.wait_for_url(f"{base}/trips/{target_id}")
        page.wait_for_load_state("networkidle")
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert serious(page) == set()
        page.goto(f"{base}/")
        page.wait_for_load_state("networkidle")
        assert page.locator(".trip-grid .card").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        browser.close()
    with sessions() as s:
        assert s.get(Trip, source_id) is None
        assert s.query(Itinerary).filter_by(trip_id=target_id).count() == before + 1
        assert s.scalar(select(Itinerary.pinned).where(Itinerary.trip_id == target_id,
                                                       Itinerary.fingerprint == fp)) is True
