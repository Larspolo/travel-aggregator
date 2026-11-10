"""The keep mark of a capture (#2018): the retention cleanup does not delete a kept capture, and the
`POST /captures/{id}/keep` form sets or clears it."""

import json
from datetime import datetime, timedelta, timezone

from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models import Capture, Trip
from app.retention import delete_old_captures
from tests.test_capture_retention import _capture, engine  # noqa: F401  (fixture: migrated empty database)
from tests.test_reparse import FIX, _capture_id, _csrf, _ingest, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_booked import _alembic

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def test_kept_capture_of_40_days_stays_and_unkept_one_goes(engine):  # noqa: F811
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        kept = _capture(s, trip.id, NOW - timedelta(days=40))
        kept.kept = True
        unkept = _capture(s, trip.id, NOW - timedelta(days=40))
        s.commit()
        kept_id, unkept_id = kept.id, unkept.id
    with Session(engine) as s:
        assert delete_old_captures(s, 30, NOW) == 1
        s.commit()
    with Session(engine) as s:
        assert s.get(Capture, kept_id) is not None
        assert s.get(Capture, unkept_id) is None


def _kept(sessions, capture_id):
    with sessions() as s:
        return s.get(Capture, capture_id).kept


def test_keep_one_sets_and_keep_zero_clears_the_mark(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    cap_id = _capture_id(sessions, trip_id)
    page = f"/trips/{trip_id}/captures"
    assert _kept(sessions, cap_id) is False
    r = c.post(f"/captures/{cap_id}/keep", data={"keep": "1", "csrf_token": _csrf(c, page)}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/captures/{cap_id}/raw"
    assert _kept(sessions, cap_id) is True
    r = c.post(f"/captures/{cap_id}/keep", data={"keep": "0", "csrf_token": _csrf(c, page)}, follow_redirects=False)
    assert r.status_code == 303
    assert _kept(sessions, cap_id) is False


def test_keep_without_csrf_token_changes_nothing(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    cap_id = _capture_id(sessions, trip_id)
    r = c.post(f"/captures/{cap_id}/keep", data={"keep": "1"}, follow_redirects=False)
    assert r.status_code == 403
    assert _kept(sessions, cap_id) is False


def test_keep_unknown_capture_is_404_and_changes_nothing(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    page = f"/trips/{trip_id}/captures"
    r = c.post("/captures/999999/keep", data={"keep": "1", "csrf_token": _csrf(c, page)}, follow_redirects=False)
    assert r.status_code == 404


def test_keep_other_value_is_422(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    cap_id = _capture_id(sessions, trip_id)
    page = f"/trips/{trip_id}/captures"
    r = c.post(f"/captures/{cap_id}/keep", data={"keep": "yes", "csrf_token": _csrf(c, page)}, follow_redirects=False)
    assert r.status_code == 422
    assert _kept(sessions, cap_id) is False


def test_migration_0049_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0049")
    eng = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(eng).get_columns("captures")}
        assert "kept" in cols()
        command.downgrade(cfg, "0048")
        assert "kept" not in cols()
        assert "parsed_with" in cols()
        command.upgrade(cfg, "0049")
        assert "kept" in cols()
    finally:
        eng.dispose()
