"""The panel shows how many captures wait in the queue and how old the oldest is (#1664)."""

import os

import pytest

from tests.test_userscript_queue import CORE, STUBS, status

pytestmark = pytest.mark.slow


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<html><body></body></html>")
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text())
        yield pg
        browser.close()


def old_items(page, count, minutes):
    """Queue `count` items that were captured `minutes` ago (the queue of the stub store, #1664)."""
    page.evaluate("""([n, m]) => {
        const at = new Date(Date.now() - m * 60000).toISOString();
        window.__gm.queue = Array.from({length: n}, (_, i) => ({trip_id: 1, source: 'test', seq: i, captured_at: at, offers: [{i: 0}]}));
    }""", [count, minutes])


def payload(n):
    return {"trip_id": 1, "source": "test", "offers": [{"i": k} for k in range(n)]}


def test_failed_send_shows_count_and_age(page):
    page.evaluate("window.__status = 0")
    old_items(page, 2, 12)
    page.evaluate("p => TACore.send(p)", payload(1))
    assert len(page.evaluate("TACore.queue()")) == 3
    assert status(page) == "Send failed: 3 captures wait (oldest 12 min), kept in the queue"


def test_auto_send_off_shows_count_and_age(page):
    page.evaluate("window.__gm.autosend = false")
    old_items(page, 2, 12)
    page.evaluate("p => TACore.send(p)", payload(3))
    assert page.evaluate("window.__sent") == []
    assert status(page) == "Captured 3 offers: 3 captures wait (oldest 12 min), press Send"


def test_one_item_says_capture_waits(page):
    page.evaluate("window.__gm.autosend = false")
    page.evaluate("p => TACore.send(p)", payload(2))
    assert status(page) == "Captured 2 offers: 1 capture waits, press Send"


def test_good_send_that_empties_the_queue_shows_sent(page):
    old_items(page, 2, 12)
    page.evaluate("TACore.flush()")
    assert page.evaluate("TACore.queue()") == []
    page.evaluate("p => TACore.send(p)", payload(3))
    assert status(page) == "Captured 3 offers → sent ✓"
