"""A queued capture with no trip gets the trip of the panel when the person chooses one (#2200).

Before the fix, the first payload with no trip_id stayed first in the queue for ever: flush() stopped at its "retry",
so each later capture waited behind it."""
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


def capture(seq, key):
    return {"source": "eurostar.com", "seq": seq, "capture_key": key, "offers": [{"i": 0}]}


def test_queued_capture_gets_the_chosen_trip(page):
    page.evaluate("p => TACore.send(p)", capture(1, "k1"))
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [1]
    assert "trip_id" not in page.evaluate("TACore.queue()")[0]
    key = page.evaluate("TACore.queue()")[0]["capture_key"]
    assert status(page) == "Choose a trip in the panel"
    assert page.evaluate("window.__sent") == []

    page.evaluate("window.GM_setValue('trip', 7)")
    page.evaluate("TACore.flush()")
    page.wait_for_function("TACore.queue().length === 0")

    sent = page.evaluate("window.__sent")
    assert len(sent) == 1
    assert sent[0]["body"]["trip_id"] == 7
    assert sent[0]["body"]["capture_key"] == key


def test_later_captures_are_not_blocked(page):
    page.evaluate("p => TACore.send(p)", capture(1, "k1"))
    page.evaluate("p => TACore.send(p)", capture(2, "k2"))
    page.evaluate("window.GM_setValue('trip', 7)")
    page.evaluate("TACore.flush()")
    page.wait_for_function("TACore.queue().length === 0")

    sent = page.evaluate("window.__sent")
    assert [s["body"]["seq"] for s in sent] == [1, 2]
    assert all(s["body"]["trip_id"] == 7 for s in sent)
