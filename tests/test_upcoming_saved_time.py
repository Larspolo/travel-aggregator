"""The saved Upcoming page says when it was saved, offline only (#965)."""

import pytest

from tests.browser_wait import wait_js
import tests.test_upcoming_offline as offline
from tests.test_upcoming_offline import CACHED, login

live = offline.live  # the fixtures of the Upcoming offline tests
page = offline.page

pytestmark = pytest.mark.slow

NOTE_SHOWN = "(() => { const n = document.querySelector('.offline-note'); return !!n && !n.hidden; })()"
NOTE_HIDDEN = "(() => { const n = document.querySelector('.offline-note'); return !!n && n.hidden; })()"
# the time of the save in the local time of the browser, as offline.js formats it
SAVED_HHMM = ("(() => { const d = new Date(document.querySelector('.offline-note').dataset.savedAt);"
              " const two = (n) => String(n).padStart(2, '0');"
              " return two(d.getHours()) + ':' + two(d.getMinutes()); })()")


def save_visit(page, live):
    login(page, live)
    page.goto(live + "/upcoming")
    wait_js(page, "navigator.serviceWorker.ready.then(r => !!r.active)")
    wait_js(page, f"{CACHED}.then(p => p.includes('/upcoming') && p.includes('/static/offline.js'))")


def test_offline_the_line_shows_the_time_of_the_save(live, page):
    save_visit(page, live)
    saved_at = page.evaluate(SAVED_HHMM)
    page.context.set_offline(True)
    page.reload()
    wait_js(page, NOTE_SHOWN)
    assert page.inner_text(".offline-note") == f"Offline: saved at {saved_at}"


def test_online_the_line_is_hidden(live, page):
    save_visit(page, live)
    page.context.set_offline(True)
    page.reload()
    wait_js(page, NOTE_SHOWN)
    page.context.set_offline(False)
    wait_js(page, NOTE_HIDDEN)


def test_the_line_causes_no_sideways_scroll_at_390_px(live, page):
    save_visit(page, live)
    page.set_viewport_size({"width": 390, "height": 844})
    page.context.set_offline(True)
    page.reload()
    wait_js(page, NOTE_SHOWN)
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0
