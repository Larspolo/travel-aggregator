"""The userscript queue keeps at most 20 captures; a 21st drops the oldest one (#1665, P3)."""

import pytest

import tests.test_userscript_queue as queue_tests

pytestmark = pytest.mark.slow
page = queue_tests.page  # the browser fixture of the queue tests
payload = queue_tests.payload
status = queue_tests.status


def fill(pg, count):
    pg.evaluate("n => { window.__gm.queue = Array.from({length: n}, (_, i) => ({trip_id: 1, source: 'test', seq: i + 1, offers: []})); }", count)


def test_21st_capture_drops_the_oldest(page):
    fill(page, 20)
    page.evaluate("window.__status = 0")
    page.evaluate("p => TACore.send(p)", payload(21, 1))
    seqs = [p["seq"] for p in page.evaluate("TACore.queue()")]
    assert len(seqs) == 20
    assert seqs[0] == 2
    assert seqs[-1] == 21


def test_panel_shows_one_old_capture_dropped(page):
    fill(page, 20)
    page.evaluate("window.__status = 0")
    page.evaluate("p => TACore.send(p)", payload(21, 1))
    assert status(page).startswith("1 old capture dropped. ")


def test_19_plus_one_drops_nothing(page):
    fill(page, 19)
    page.evaluate("window.__status = 0")
    page.evaluate("p => TACore.send(p)", payload(20, 1))
    assert len(page.evaluate("TACore.queue()")) == 20
    assert "dropped" not in status(page)
