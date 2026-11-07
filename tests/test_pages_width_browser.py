"""Each page of the app fits the screen at a phone width and at 640 px: no sideways scroll, no element outside (#759)."""

import os

import pytest

from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow

PATHS = ["/", "/?archived=1", "/trips/new", "/trips/{id}/edit", "/trips/{id}/delete", "/trips/{id}",
         "/trips/{id}/compare?it={it0}&it={it1}&it={it2}", "/tokens", "/places", "/rates", "/profiles", "/captures", "/trips/{id}/captures",
         "/settings", "/trips/{id}/itineraries/{it0}/history"]

OUTSIDE = """(w) => [...document.querySelectorAll('body *')].filter(e => {
  const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  if (!r.width || !r.height || s.visibility === 'hidden') return false;
  for (let a = e.parentElement; a; a = a.parentElement) {
    const o = getComputedStyle(a).overflowX;
    if (o === 'auto' || o === 'scroll' || o === 'hidden') return false;
  }
  return r.left < -0.5 || r.right > w + 0.5;
}).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().left) + '..'
  + Math.round(e.getBoundingClientRect().right))"""


@pytest.mark.parametrize("width", [390, 640])
@pytest.mark.parametrize("path", PATHS)
def test_each_page_fits_the_screen(live, days_trip, sessions, path, width):  # noqa: F811
    from sqlalchemy import select

    from app.models import Itinerary

    with sessions() as s:
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == days_trip).order_by(Itinerary.id)).all()
    from playwright.sync_api import sync_playwright

    base = live.rsplit("/trips/", 1)[0]
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 844})
        response = page.goto(base + path.format(id=days_trip, it0=ids[0], it1=ids[1], it2=ids[2]))
        status = response.status
        page.wait_for_load_state("networkidle")
        scroll = page.evaluate("document.documentElement.scrollWidth")
        outside = page.evaluate(OUTSIDE, width)
        browser.close()
    assert status == 200, f"{path} answers {status}"
    assert scroll <= width, f"{path} scrolls sideways: {scroll} px"
    assert not outside, f"{path}: elements outside the screen: {outside[:5]}"
