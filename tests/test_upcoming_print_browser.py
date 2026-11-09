"""The browser print of the Upcoming page shows only the journeys on 1 A4 page: no app bar, button or the section
"Calendar" (#1349)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.test_a11y_browser import launch
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow

DEPART = datetime.now(timezone.utc).replace(hour=6, minute=5, second=0, microsecond=0) + timedelta(days=10)
LEGS = [("NS", "IC 141", "Amsterdam", "Utrecht"), ("DB", "ICE 105", "Utrecht", "Basel"),
        ("SBB", "IR 2517", "Basel", "Zürich")]


def test_the_print_of_upcoming_shows_only_the_journeys_on_one_page(live, days_trip, sessions):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from app.models import Itinerary, Leg

    legs, at = [], DEPART
    for seq, (carrier, number, src, dst) in enumerate(LEGS):
        legs.append(Leg(seq=seq, mode="train", carrier=carrier, service_no=number, from_name=src, to_name=dst,
                        depart_at=at, depart_offset_min=60, arrive_at=at + timedelta(hours=1),
                        arrive_offset_min=60))
        at += timedelta(hours=2)
    with sessions() as s:
        s.add(Itinerary(trip_id=days_trip, fingerprint="print-1349", depart_at=DEPART, arrive_at=legs[-1].arrive_at,
                        duration_min=300, booked=True, booked_price=Decimal("123.45"), booked_currency="EUR",
                        legs=legs))
        s.commit()
    base = live.rsplit("/trips/", 1)[0]
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 794, "height": 1123})
        page.goto(base + "/upcoming")
        page.wait_for_load_state("networkidle")
        page.emulate_media(media="print")
        text = page.inner_text("main")
        hidden = {sel: [page.locator(sel).nth(i).is_visible() for i in range(page.locator(sel).count())]
                  for sel in ("nav.topbar", "button", ".calendar-feed", "form", "a.icon")}
        pdf = page.pdf(format="A4")
        browser.close()
    for i, (carrier, number, src, dst) in enumerate(LEGS):
        dep = (DEPART + timedelta(hours=2 * i, minutes=60)).strftime("%H:%M")
        assert f"{carrier} {number}" in text and f"{src} → {dst}" in text and dep in text, text
    assert "123.45" in text, text
    for sel, shown in hidden.items():
        assert not any(shown), f"{sel} shows in the print"
    pages = len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))
    assert pages == 1, f"the print has {pages} pages"
