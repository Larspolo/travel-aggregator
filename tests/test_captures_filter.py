"""The captures pages filter to the failed captures with ?failed=1 (#349)."""

import re
from datetime import datetime, timezone

from app.models import Capture
from tests.test_reparse import setup as reparse_setup  # noqa: F401  (fixture: logged-in client)


def _data_rows(text):
    rows = re.findall(r"<tr>(.*?)</tr>", text, re.S)
    return [r for r in rows if "<td" in r]


def _add_capture(sessions, trip_id, **fields):
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source="bahn.de", captured_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
                      **fields))
        s.commit()


def _pages(trip_id):
    return (f"/trips/{trip_id}/captures", "/captures")


def test_failed_filter_shows_only_the_failed_capture_on_both_pages(reparse_setup, sessions):  # noqa: F811
    c, auth, trip_id = reparse_setup
    _add_capture(sessions, trip_id, offer_count=2, rejected_count=0, errors_json=[])
    _add_capture(sessions, trip_id, offer_count=1, rejected_count=1,
                 errors_json=[{"index": 0, "reason": "bad price"}])
    for page in _pages(trip_id):
        everything = c.get(page).text
        assert len(_data_rows(everything)) == 2, page
        assert "Only failed captures" in everything, page

        failed = c.get(page + "?failed=1").text
        rows = _data_rows(failed)
        assert len(rows) == 1, page
        assert "capture-failed" in rows[0], page
        assert "Show all captures" in failed, page
        assert "Only failed captures" not in failed, page


def test_failed_filter_with_only_good_captures_says_no_failed_captures(reparse_setup, sessions):  # noqa: F811
    c, auth, trip_id = reparse_setup
    _add_capture(sessions, trip_id, offer_count=2, rejected_count=0, errors_json=[])
    for page in _pages(trip_id):
        text = c.get(page + "?failed=1").text
        assert "No failed captures." in text, page
        assert _data_rows(text) == [], page
