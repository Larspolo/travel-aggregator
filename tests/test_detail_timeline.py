"""The open "Legs and fares" detail of an itinerary (#662): the legs as a timeline with no numbered list, the
transfer duration, a "Book" button per fare with a booking URL, and a labelled note field."""

import os
import re

import pytest

from tests.test_history_row import live  # noqa: F401  (fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def detail(page):
    start = page.index('<tr class="detail">')
    return page[start:page.index("</details>", start)]


def test_the_detail_shows_a_timeline_book_buttons_and_a_labelled_note(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = offer("89.90")
    o["booking_url"] = "https://example.test/book"
    ingest(client, auth, trip_id, [o])
    d = detail(client.get(f"/trips/{trip_id}").text)
    assert "<ol" not in d and "<li" not in d
    assert d.count('class="leg"') == 2 and re.search(r"Transfer at [^:]+: \dh \d\d", d)
    assert len(re.findall(r"<time>\d\d:\d\d</time>", d)) == 4
    book = re.search(r'<a class="btn"[^>]*>', d).group(0)
    assert 'rel="noopener noreferrer"' in book and 'target="_blank"' in book
    m = re.search(r'<label for="(note-\d+)">Note</label>', d)
    assert m and f'id="{m.group(1)}"' in d


@pytest.mark.slow
def test_screenshots_of_an_open_detail(live):  # noqa: F811
    from playwright.sync_api import sync_playwright

    out = os.environ.get("SCREENSHOT_DIR")
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        for width in (1280, 390):
            for scheme in ("light", "dark"):
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2,
                                        color_scheme=scheme)
                page.goto(live)
                page.locator("details summary", has_text="Legs and fares").first.click()
                page.wait_for_selector("table.history, .history")
                assert page.evaluate("document.documentElement.scrollWidth") <= width
                if out:
                    page.locator("tr.detail").first.screenshot(path=f"{out}/detail-{width}-{scheme}.png")
                page.close()
        browser.close()
