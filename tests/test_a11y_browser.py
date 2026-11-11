"""Each page of the app has no new "serious" or "critical" axe-core finding at 1280 and 390 px (#817).

`KNOWN` lists the findings of main at the time of #817. A fix must remove its entry: the test also fails on an entry
that no longer occurs.
"""

import os

import pytest

from tests.test_pages_width_browser import PATHS
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow

# (path, width) -> rule ids. The key has the width: some findings occur only at 390 px (a table that scrolls sideways).
KNOWN: dict[tuple[str, int], set[str]] = {}


def serious(page) -> set[str]:
    """Return the rule ids of the "serious" and "critical" axe-core violations on the page."""
    from axe_playwright_python.sync_playwright import Axe

    result = Axe().run(page)
    return {v["id"] for v in result.response["violations"] if v.get("impact") in ("serious", "critical")}


def check(path: str, width: int, found: set[str]) -> None:
    known = KNOWN.get((path, width), set())
    assert not found - known, f"{path} at {width} px: new axe findings {sorted(found - known)}"
    assert not known - found, f"{path} at {width} px: KNOWN entries that no longer occur, remove them: {sorted(known - found)}"


def launch(p):
    exe = "/opt/pw-browsers/chromium"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("path", PATHS)
def test_each_page_has_no_new_axe_finding(live, days_trip, sessions, path, width):  # noqa: F811
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select

    from app.models import Itinerary

    with sessions() as s:
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == days_trip).order_by(Itinerary.id)).all()
    base = live.rsplit("/trips/", 1)[0]
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 844})
        response = page.goto(base + path.format(id=days_trip, it0=ids[0], it1=ids[1], it2=ids[2]))
        page.wait_for_load_state("networkidle")
        found = serious(page)
        browser.close()
    assert response.status == 200, f"{path} answers {response.status}"
    check(path, width, found)


def test_a_new_finding_and_a_stale_entry_fail(monkeypatch):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        page.set_content('<html lang="en"><head><title>t</title></head><body><main><input type="text"></main></body></html>')
        found = serious(page)
        browser.close()
    assert "label" in found
    with pytest.raises(AssertionError, match=r"/x at 390 px: new axe findings \['label'\]"):
        check("/x", 390, found)
    monkeypatch.setitem(KNOWN, ("/x", 390), found | {"color-contrast"})
    with pytest.raises(AssertionError, match="no longer occur.*color-contrast"):
        check("/x", 390, found)
