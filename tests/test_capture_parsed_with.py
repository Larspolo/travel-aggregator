"""The server parser version that parsed each capture (#1989): `captures.parsed_with`. The userscript version
(`parser_version`) keeps the value that the client sent."""

import json

from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import Capture
from app.parsers.bahn import BahnParser
from tests.test_reparse import FIX, _capture_id, _csrf, _ingest, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_booked import _alembic


def _row(sessions, trip_id):
    with sessions() as s:
        c = s.scalar(select(Capture).where(Capture.trip_id == trip_id))
        return c.parsed_with, c.parser_version


def test_a_new_capture_stores_the_version_of_the_server_parser(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    assert _row(sessions, trip_id) == (BahnParser.version, "0.0.1")


def test_a_reparse_after_a_parser_change_stores_the_new_version(setup, sessions, monkeypatch):  # noqa: F811
    c, auth, trip_id = setup
    _ingest(c, auth, trip_id, json.loads(FIX.read_text(encoding="utf-8")))
    monkeypatch.setattr(BahnParser, "version", "9.9.9")
    page = f"/trips/{trip_id}/captures"
    r = c.post(f"/captures/{_capture_id(sessions, trip_id)}/reparse", headers={"X-CSRF-Token": _csrf(c, page)})
    assert r.status_code == 200
    assert _row(sessions, trip_id) == ("9.9.9", "0.0.1")


def test_migration_0048_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("captures")}
        assert "parsed_with" in cols()
        command.downgrade(cfg, "0047")
        assert "parsed_with" not in cols()
        command.upgrade(cfg, "head")
        assert "parsed_with" in cols()
    finally:
        engine.dispose()
