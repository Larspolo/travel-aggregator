"""Each capture stores the number of travelers of its prices (#764)."""

import json
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select, text

from app import ingest
from app.models import Capture
from tests.test_capture_mismatch import _csrf, _setup
from tests.test_trip_booked import _alembic

FIXTURES = Path(__file__).parent / "fixtures"
# the 1-adult fixtures; the 2-adult fixture of #767 is in tests/test_rank_travelers.py
CASES = [("bahn.de", f.name) for f in sorted((FIXTURES / "bahn.de").glob("fahrplan-*.json")) if "-2-adults" not in f.name] + [
    (src, f.name) for src in ("nsinternational.com", "flixbus.com") for f in sorted((FIXTURES / src).glob("*.json"))]
BAHN = FIXTURES / "bahn.de" / "fahrplan-koeln-muenchen.json"


def _ingest(c, auth, trip_id, source, raw, context=None):
    body = {"trip_id": trip_id, "source": source, "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    if context is not None:
        body["search_context"] = context
    r = c.post("/api/ingest", headers=auth, json=body)
    assert r.status_code < 300, r.text


def _capture(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Capture).where(Capture.trip_id == trip_id))


@pytest.mark.parametrize("source,name", CASES)
def test_each_fixture_stores_one_traveler(sessions, monkeypatch, source, name):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, source, json.loads((FIXTURES / source / name).read_text(encoding="utf-8")))
    assert _capture(sessions, trip_id).travelers == 1


def test_no_count_and_no_context_stores_none(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, "bahn.de", json.loads(BAHN.read_text(encoding="utf-8"))["response"])
    assert _capture(sessions, trip_id).travelers is None


def test_two_reisende_store_two(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    raw = json.loads(BAHN.read_text(encoding="utf-8"))
    raw["request"]["reisende"][0]["anzahl"] = 2
    _ingest(c, auth, trip_id, "bahn.de", raw)
    assert _capture(sessions, trip_id).travelers == 2
    assert "2 travelers" in c.get(f"/trips/{trip_id}/captures").text


@pytest.mark.parametrize("value,expected", [(3, 3), (0, None), (10, None), ("3", None), (True, None)])
def test_the_search_context_gives_the_count(sessions, monkeypatch, value, expected):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    raw = json.loads(BAHN.read_text(encoding="utf-8"))["response"]
    _ingest(c, auth, trip_id, "bahn.de", raw, context={"travelers": value})
    assert _capture(sessions, trip_id).travelers == expected


def test_the_page_shows_one_traveler(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, "bahn.de", json.loads(BAHN.read_text(encoding="utf-8")))
    page = c.get("/captures").text
    assert "1 traveler<" in page


def test_a_reparse_sets_the_count_again(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, "bahn.de", json.loads(BAHN.read_text(encoding="utf-8")))
    with sessions() as s:
        cap = s.scalar(select(Capture).where(Capture.trip_id == trip_id))
        cap.travelers = None
        s.commit()
        cid = cap.id
    page = f"/trips/{trip_id}/captures"
    assert c.post(f"/captures/{cid}/reparse", headers={"X-CSRF-Token": _csrf(c, page)}).status_code == 200
    assert _capture(sessions, trip_id).travelers == 1


def test_parse_result_count_rejects_bad_values():
    from app.parsers import count
    from app.parsers.flixbus import travelers
    assert [count(v) for v in (1, 9, 0, 10, None, 2.0)] == [1, 9, None, None, None, None]
    assert travelers("https://x/?products=%7B%22adult%22%3A2%2C%22child%22%3A1%7D") == 3
    assert travelers("https://x/?products=bad") is None and travelers(None) is None
    assert ingest.count is count


def test_migration_0018_up_and_down_with_captures(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0017")
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO trips (title, origin_text, destination_text) VALUES ('t', 'a', 'b')"))
            conn.execute(text("INSERT INTO captures (trip_id, source, captured_at) "
                              "SELECT id, 'bahn.de', now() FROM trips"))

        def cols():
            return {c["name"] for c in inspect(engine).get_columns("captures")}
        command.upgrade(cfg, "head")
        assert "travelers" in cols()
        command.downgrade(cfg, "0017")
        assert "travelers" not in cols()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM captures")).scalar() == 1
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()


