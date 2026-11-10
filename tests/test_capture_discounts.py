"""Each capture stores the discount cards of its prices (#1750, epic #1749)."""

import json
from pathlib import Path

from alembic import command
from sqlalchemy import select

from app import ingest
from app.models import Capture
from tests.test_capture_mismatch import _setup
from tests.test_capture_travelers import _capture, _ingest
from tests.test_trip_booked import _alembic

FIXTURES = Path(__file__).parent / "fixtures"
CARD = FIXTURES / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
NO_CARD = FIXTURES / "bahn.de" / "fahrplan-koeln-muenchen.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_bahncard_capture_stores_the_card(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, "bahn.de", _load(CARD))
    assert _capture(sessions, trip_id).discounts == ["BahnCard 25"]


def test_a_capture_without_a_card_stores_an_empty_list(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, "bahn.de", _load(NO_CARD))
    assert _capture(sessions, trip_id).discounts == []


def test_a_source_without_the_field_stores_null(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    flix = sorted((FIXTURES / "flixbus.com").glob("*.json"))[0]
    _ingest(c, auth, trip_id, "flixbus.com", _load(flix))
    assert _capture(sessions, trip_id).discounts is None


def test_a_reparse_sets_the_cards_again(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _ingest(c, auth, trip_id, "bahn.de", _load(CARD))
    with sessions() as s:
        cap = s.scalar(select(Capture).where(Capture.trip_id == trip_id))
        cap.discounts = None
        s.commit()
    with sessions() as s:
        cap = s.scalar(select(Capture).where(Capture.trip_id == trip_id))
        ingest.reparse(s, cap)
        s.refresh(cap)
        assert cap.discounts == ["BahnCard 25"]


def test_the_migration_downgrades_to_0037_and_upgrades(empty_database_url):
    from sqlalchemy import create_engine, inspect

    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0037")
    eng = create_engine(empty_database_url)
    assert "discounts" not in {c["name"] for c in inspect(eng).get_columns("captures")}
    command.upgrade(cfg, "head")
    assert "discounts" in {c["name"] for c in inspect(eng).get_columns("captures")}
    eng.dispose()
