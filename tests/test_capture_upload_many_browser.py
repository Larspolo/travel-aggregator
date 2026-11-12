"""The file field of the captures page takes several files, and the page shows one result line per file (#2529)."""

from pathlib import Path

import pytest

from tests.test_a11y_browser import launch
from tests.test_trip_days_browser import days_trip, live  # noqa: F401  (fixtures: the trip and the live server)

pytestmark = pytest.mark.slow

FIX = Path(__file__).parent / "fixtures"


def test_the_upload_field_takes_several_files_and_shows_one_line_per_file(live, days_trip, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    bahn = tmp_path / "bahn.de-12.json"
    bahn.write_bytes((FIX / "bahn.de" / "fahrplan-amsterdam-berlin.json").read_bytes())
    flix = tmp_path / "flixbus.com-14.json"
    flix.write_bytes((FIX / "flixbus.com" / "search-amsterdam-berlin.json").read_bytes())
    notes = tmp_path / "notes.txt"
    notes.write_text("Not a payload.", encoding="utf-8")

    url = live.rsplit("/trips/", 1)[0] + f"/trips/{days_trip}/captures"
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 844})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        multiple = page.get_attribute("#u-file", "multiple")
        page.set_input_files("#u-file", [str(bahn), str(flix), str(notes)])
        with page.expect_navigation():
            page.click("#upload-payload button[type=submit]")
        page.wait_for_load_state("networkidle")
        lines = page.locator("ul.upload-results li").all_inner_texts()
        browser.close()

    assert multiple is not None, "the upload field has no multiple attribute"
    assert len(lines) == 3, f"expected one result line per file, got {lines}"
    assert lines[0].startswith("bahn.de-12.json: stored"), lines
    assert lines[1].startswith("flixbus.com-14.json: stored"), lines
    assert lines[2].startswith("notes.txt: not stored"), lines
