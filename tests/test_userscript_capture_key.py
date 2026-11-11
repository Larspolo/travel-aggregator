"""The userscript gives each queued capture a `capture_key` once (#1868), and a 409 keeps the payload in the queue."""

import os
import re

import pytest

from tests.test_userscript_429 import CORE, STUBS, payload, status

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


def queued_keys(page):
    return [item.get("capture_key") for item in page.evaluate("TACore.queue()")]


def test_queued_payload_has_a_36_character_key(page):
    page.evaluate("window.__status = 429")
    page.evaluate("p => TACore.send(p)", payload(1))
    (key,) = queued_keys(page)
    assert len(key) == 36
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", key)


def test_resend_posts_the_same_key(page):
    page.evaluate("window.__status = 429")
    page.evaluate("p => TACore.send(p)", payload(2))
    (key,) = queued_keys(page)
    page.evaluate("window.__status = 0")  # network error: the payload stays in the queue
    page.evaluate("TACore.flush()")
    page.evaluate("window.__status = 200; window.__sent = []")
    page.evaluate("TACore.flush()")
    sent = page.evaluate("window.__sent")
    assert [s["body"]["capture_key"] for s in sent] == [key]
    assert page.evaluate("TACore.queue()") == []


def test_two_captures_have_two_keys(page):
    page.evaluate("window.__status = 429")
    page.evaluate("p => TACore.send(p)", payload(3))
    page.evaluate("p => TACore.send(p)", payload(4))
    first, second = queued_keys(page)
    assert first != second


def test_409_keeps_payload_and_200_removes_it(page):
    page.evaluate("window.__status = 409")
    page.evaluate("p => TACore.send(p)", payload(5))
    assert status(page) == "Server busy: kept in the queue"
    assert [p["seq"] for p in page.evaluate("TACore.queue()")] == [5]
    page.evaluate("window.__status = 200; window.__sent = []")
    page.evaluate("TACore.flush()")
    assert [s["body"]["seq"] for s in page.evaluate("window.__sent")] == [5]
    assert page.evaluate("TACore.queue()") == []


def test_queue_item_without_key_is_sent_without_key(page):
    page.evaluate("window.__gm.queue = [{trip_id: 1, source: 'test', seq: 7, offers: [{i: 0}]}]")
    page.evaluate("window.__status = 200")
    page.evaluate("TACore.flush()")
    sent = page.evaluate("window.__sent")
    assert [s["body"]["seq"] for s in sent] == [7]
    assert "capture_key" not in sent[0]["body"]
