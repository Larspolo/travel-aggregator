"""Each control that Tab reaches shows a focus mark on each page of the app, at 1280 and 390 px (#834)."""

import pytest

from tests.test_a11y_browser import launch
from tests.test_pages_width_browser import PATHS
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow

FOCUSED = """() => { const e = document.activeElement; if (!e || e === document.body) return null;
  const s = getComputedStyle(e);
  const mark = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
  return {key: e.outerHTML.slice(0, 120), mark}; }"""


def tab_stops(page, limit=200):
    """Press Tab until the focus leaves the page or comes back; return (seen, the stops with no mark)."""
    missing, seen = [], []
    for _ in range(limit):
        page.keyboard.press("Tab")
        info = page.evaluate(FOCUSED)
        if info is None or info["key"] in seen:
            break
        seen.append(info["key"])
        if not info["mark"]:
            missing.append(info["key"])
    return seen, missing


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("path", PATHS)
def test_each_tab_stop_of_each_page_has_a_focus_mark(live, days_trip, sessions, path, width):  # noqa: F811
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select

    from app.models import Itinerary

    with sessions() as s:
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == days_trip).order_by(Itinerary.id)).all()
    base = live.rsplit("/trips/", 1)[0]
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(base + path.format(id=days_trip, it0=ids[0], it1=ids[1], it2=ids[2]))
        page.wait_for_load_state("networkidle")
        seen, missing = tab_stops(page)
        browser.close()
    assert seen, f"{path} at {width} px: no Tab stop"
    assert not missing, f"{path} at {width} px: no focus mark: {missing}"


def test_an_element_with_no_mark_is_found():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        page.set_content('<style>a:focus{outline:none}</style><button>ok</button><a href="#x">bad</a>')
        seen, missing = tab_stops(page)
        browser.close()
    assert len(seen) == 2 and missing == ['<a href="#x">bad</a>']
