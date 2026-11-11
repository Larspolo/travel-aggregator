"""Each capture keeps the result of its last parse (#346)."""

import copy
import json

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app import ingest
from app.models import Capture
from tests.test_ingest_api import BODY, setup  # noqa: F401  (fixture)
from tests.test_ingest_rejected import offer
from tests.test_reparse import FIX, BrokenParser, _capture_id, _csrf, _ingest
from tests.test_reparse import setup as reparse_setup  # noqa: F401  (fixture)
from tests.test_trip_booked import _alembic

COLUMNS = {"offer_count", "rejected_count", "errors_json", "unreadable"}


def _capture(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Capture).where(Capture.trip_id == trip_id))


def test_a_batch_stores_the_counts_and_the_errors(setup, sessions):  # noqa: F811
    client, auth, trip_id = setup
    offers = [offer("ICE 1"), offer("ICE 2", price_currency="<script>"), offer("ICE 3")]
    r = client.post("/api/ingest", json={**copy.deepcopy(BODY), "trip_id": trip_id, "offers": offers}, headers=auth)
    assert r.status_code == 200
    c = _capture(sessions, trip_id)
    assert (c.offer_count, c.rejected_count, c.unreadable) == (2, 1, None)
    assert c.errors_json[0]["index"] == 1 and "price_currency" in c.errors_json[0]["reason"]
    assert "<script>" not in json.dumps(c.errors_json)


class UnreadableParser:
    source, version = "bahn.de", "0.0.1"

    def parse(self, raw):
        raise ValueError("no journeys")


def test_an_unreadable_payload_sets_unreadable(reparse_setup, sessions, monkeypatch):  # noqa: F811
    c, auth, trip_id = reparse_setup
    monkeypatch.setattr(ingest, "get_parser", lambda source: UnreadableParser())
    _ingest(c, auth, trip_id, {"x": 1})
    cap = _capture(sessions, trip_id)
    assert cap.unreadable == "no journeys" and cap.offer_count == 0 and cap.rejected_count == 0


def test_a_reparse_replaces_the_stored_result(reparse_setup, sessions, monkeypatch):  # noqa: F811
    c, auth, trip_id = reparse_setup
    with monkeypatch.context() as m:
        m.setattr(ingest, "get_parser", lambda source: UnreadableParser())
        _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    assert _capture(sessions, trip_id).unreadable == "no journeys"
    with monkeypatch.context() as m:
        m.setattr(ingest, "get_parser", lambda source: BrokenParser())
        cid = _capture_id(sessions, trip_id)
        page = f"/trips/{trip_id}/captures"
        assert c.post(f"/captures/{cid}/reparse", headers={"X-CSRF-Token": _csrf(c, page)}).status_code == 200
    cap = _capture(sessions, trip_id)
    assert cap.unreadable is None and cap.offer_count == 0 and cap.errors_json == []
    r = c.post(f"/captures/{cid}/reparse", headers={"X-CSRF-Token": _csrf(c, page)})
    assert r.status_code == 200
    cap = _capture(sessions, trip_id)
    assert cap.unreadable is None and cap.offer_count > 0


def test_migration_0010_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("captures")}
        assert COLUMNS <= cols()
        command.downgrade(cfg, "0009")
        assert not COLUMNS & cols()
        command.upgrade(cfg, "head")
        assert COLUMNS <= cols()
    finally:
        engine.dispose()
