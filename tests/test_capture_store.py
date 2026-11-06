"""The raw capture is stored compressed and loads back (#32)."""

import json
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.ingest import load_raw, store_capture
from app.models import Capture, Trip
from app.schemas import IngestIn


def _alembic(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def engine(empty_database_url):
    command.upgrade(_alembic(empty_database_url), "head")
    eng = create_engine(empty_database_url)
    yield eng
    eng.dispose()


def _store(engine, raw):
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        body = IngestIn.model_construct(trip_id=trip.id, source="ns", parser_version="1",
                                        captured_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
                                        page_url="https://example.org/s", search_context={"from": "Utrecht"},
                                        raw=raw, offers=[])
        cid = store_capture(s, trip.id, body).id
        s.commit()
    with Session(engine) as s:
        return s.get(Capture, cid)


def test_load_raw_gives_same_dict(engine):
    raw = {"journeys": [{"id": 1, "price": "12.30", "name": "Zürich → Köln"}], "n": None}
    cap = _store(engine, raw)
    assert load_raw(cap) == raw
    assert cap.page_url == "https://example.org/s" and cap.search_context_json == {"from": "Utrecht"}


def test_large_payload_is_compressed(engine):
    raw = {"rows": [{"i": i, "carrier": "NS", "text": "Intercity direct to Amsterdam"} for i in range(1600)]}
    text = json.dumps(raw)
    assert len(text) > 100_000
    cap = _store(engine, raw)
    assert len(cap.raw_gz) < len(text)
    assert load_raw(cap) == raw


def test_no_raw_stores_null(engine):
    cap = _store(engine, None)
    assert cap.raw_gz is None and load_raw(cap) is None


def test_migration_up_and_down(engine, empty_database_url):
    cfg = _alembic(empty_database_url)
    assert "captures" in inspect(engine).get_table_names()
    command.downgrade(cfg, "0001")
    assert "captures" not in inspect(engine).get_table_names()
    assert "capture_id" not in {c["name"] for c in inspect(engine).get_columns("fare_prices")}
    command.upgrade(cfg, "head")
    assert "capture_id" in {c["name"] for c in inspect(engine).get_columns("fare_prices")}
