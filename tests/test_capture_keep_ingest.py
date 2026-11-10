"""The sequence of the keep mark through the ingest (#2042, criterion 1 of #2017): a kept capture of 40 days ago stays
at an ingest; after "Do not keep" the next ingest deletes it. An unkept capture of 40 days ago goes at the first
ingest."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Capture, Setting
from app.retention import RETENTION_KEY
from tests.test_reparse import FIX, _csrf, _ingest, setup  # noqa: F401  (fixture: logged-in client)

RAW = b"raw of a capture of 40 days ago"


@pytest.fixture
def retention_30(sessions):
    """The retention period is 30 days for the test; the value that was there before is restored after it."""
    with sessions() as s:
        row = s.get(Setting, RETENTION_KEY)
        before = None if row is None else row.value
        s.merge(Setting(key=RETENTION_KEY, value="30"))
        s.commit()
    yield
    with sessions() as s:
        if before is None:
            row = s.get(Setting, RETENTION_KEY)
            if row is not None:
                s.delete(row)
        else:
            s.merge(Setting(key=RETENTION_KEY, value=before))
        s.commit()


def _old_capture(sessions, trip_id, kept):
    with sessions() as s:
        cap = Capture(trip_id=trip_id, source="bahn.de", captured_at=datetime.now(UTC) - timedelta(days=40),
                      raw_gz=RAW, kept=kept)
        s.add(cap)
        s.commit()
        return cap.id


def _state(sessions, cap_id):
    """The raw_gz of the capture, or None when its row is gone."""
    with sessions() as s:
        return s.scalar(select(Capture.raw_gz).where(Capture.id == cap_id))


def _exists(sessions, cap_id):
    with sessions() as s:
        return s.get(Capture, cap_id) is not None


def _raw():
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_kept_capture_of_40_days_stays_at_an_ingest(setup, sessions, retention_30):  # noqa: F811
    c, auth, trip_id = setup
    cap_id = _old_capture(sessions, trip_id, kept=True)
    _ingest(c, auth, trip_id, _raw())
    assert _exists(sessions, cap_id)
    assert _state(sessions, cap_id) == RAW


def test_do_not_keep_then_next_ingest_deletes_the_capture(setup, sessions, retention_30):  # noqa: F811
    c, auth, trip_id = setup
    cap_id = _old_capture(sessions, trip_id, kept=True)
    _ingest(c, auth, trip_id, _raw())
    assert _state(sessions, cap_id) == RAW
    page = f"/trips/{trip_id}/captures"
    r = c.post(f"/captures/{cap_id}/keep", data={"keep": "0", "csrf_token": _csrf(c, page)},
               follow_redirects=False)
    assert r.status_code == 303
    assert _exists(sessions, cap_id)  # the form alone deletes nothing: the next ingest does
    _ingest(c, auth, trip_id, _raw())
    assert not _exists(sessions, cap_id)


def test_unkept_capture_of_40_days_goes_at_the_first_ingest(setup, sessions, retention_30):  # noqa: F811
    c, auth, trip_id = setup
    cap_id = _old_capture(sessions, trip_id, kept=False)
    _ingest(c, auth, trip_id, _raw())
    assert not _exists(sessions, cap_id)
