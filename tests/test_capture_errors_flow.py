"""One flow: a failed capture shows its error, and a reparse after the parser fix shows the new result (#350)."""

import json
import re
from pathlib import Path

from sqlalchemy import select

from app import ingest
from app.models import Capture
from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client)
from tests.test_reparse import _csrf, _ingest

GOOD = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-amsterdam-bern-night.json"
BROKEN = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
REASON = "site format changed"


class UnreadableParser:
    source, version = "bahn.de", "0.0.1"

    def parse(self, raw):
        raise ValueError(REASON)


def _data_rows(text):
    rows = re.findall(r"<tr>(.*?)</tr>", text, re.S)
    return [r for r in rows if "<td" in r]


def _capture(sessions, **where):
    with sessions() as s:
        return s.scalar(select(Capture).filter_by(**where))


def test_failed_capture_shows_its_error_and_a_reparse_clears_it(setup, sessions, monkeypatch):  # noqa: F811
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(GOOD.read_text(encoding="utf-8")))
    with monkeypatch.context() as m:
        m.setattr(ingest, "get_parser", lambda source: UnreadableParser())
        _ingest(c, auth, trip_id, json.loads(BROKEN.read_text(encoding="utf-8")))

    failed_page = c.get("/captures?failed=1").text
    rows = _data_rows(failed_page)
    assert len(rows) == 1 and "capture-failed" in rows[0]
    assert REASON in rows[0]
    assert len(_data_rows(c.get("/captures").text)) == 2

    broken = _capture(sessions, trip_id=trip_id, unreadable=REASON)
    assert broken is not None
    cid = broken.id

    # the parser is fixed: the real parser runs again on the stored raw data
    page = "/captures?failed=1"
    r = c.post(f"/captures/{cid}/reparse", headers={"X-CSRF-Token": _csrf(c, page)})
    assert r.status_code == 200
    assert "created" in r.text

    assert "No failed captures." in c.get("/captures?failed=1").text
    fixed = _capture(sessions, id=cid)
    assert fixed.unreadable is None
    assert fixed.offer_count and fixed.offer_count > 0
    all_rows = _data_rows(c.get("/captures").text)
    assert len(all_rows) == 2
    fixed_row = next(row for row in all_rows if f'id="reparse-{cid}"' in row)
    assert f"<td>{fixed.offer_count}</td>" in fixed_row
    assert "capture-failed" not in fixed_row
