"""The captures pages show the parse result of each capture (#348)."""

import copy
import re
from datetime import datetime, timezone

from app.models import Capture
from tests.test_ingest_api import BODY
from tests.test_ingest_rejected import offer
from tests.test_reparse import setup as reparse_setup  # noqa: F401  (fixture: logged-in client)


def _rows(text):
    return re.findall(r"<tr>(.*?)</tr>", text, re.S)


def _batch(c, auth, trip_id):
    offers = [offer("ICE 1"), offer("ICE 2", price_currency="<script>")]
    r = c.post("/api/ingest", json={**copy.deepcopy(BODY), "trip_id": trip_id, "offers": offers}, headers=auth)
    assert r.status_code == 200, r.text


def _add_capture(sessions, trip_id, **fields):
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source="bahn.de", captured_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
                      **fields))
        s.commit()


def test_a_batch_with_a_bad_offer_shows_counts_and_reason_on_both_pages(reparse_setup, sessions):  # noqa: F811
    c, auth, trip_id = reparse_setup
    _batch(c, auth, trip_id)
    for page in (f"/trips/{trip_id}/captures", "/captures"):
        text = c.get(page).text
        row = next(r for r in _rows(text) if "capture-failed" in r)
        assert re.search(r"<td>1</td>\s*<td>(?:[^<]|<a [^>]*>[^<]*</a>)*</td>\s*<td>1</td>\s*<td class=\"capture-failed\">", row), page  # #2328 Changes
        assert "offer 1: " in row and "price_currency" in row, page


def test_a_good_capture_shows_ok_and_a_null_row_shows_dashes(reparse_setup, sessions):  # noqa: F811
    c, auth, trip_id = reparse_setup
    _add_capture(sessions, trip_id, offer_count=2, rejected_count=0, errors_json=[])
    _add_capture(sessions, trip_id)  # a capture from before #346: no counts
    text = c.get(f"/trips/{trip_id}/captures").text
    good = next(r for r in _rows(text) if ">ok<" in r)
    assert "capture-failed" not in good
    old = next(r for r in _rows(text) if "<td>-</td>" in r and ">ok<" not in r and "capture-failed" not in r)
    assert re.search(r"<td>-</td>\s*<td>-</td>\s*<td>-</td>", old)


def test_a_reason_with_script_is_shown_as_text(reparse_setup, sessions):  # noqa: F811
    c, auth, trip_id = reparse_setup
    _add_capture(sessions, trip_id, offer_count=0, rejected_count=1,
                 errors_json=[{"index": 0, "reason": "<script>alert(1)</script>"}])
    text = c.get(f"/trips/{trip_id}/captures").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "<script>alert(1)</script>" not in text
