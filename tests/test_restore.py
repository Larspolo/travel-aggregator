"""Restore a dump with python -m app.restore (#136)."""

import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import backup, restore
from app.ingest import store
from app.models import Trip
from app.schemas import IngestIn

PG_BIN = Path("/usr/lib/postgresql/16/bin")
TABLES = ("trips", "itineraries", "fares", "fare_prices")


@pytest.fixture
def pg_tools(monkeypatch):
    if not (PG_BIN / "pg_dump").exists() and not shutil.which("pg_dump"):
        pytest.skip("no pg_dump")
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + __import__("os").environ["PATH"])
    # A client newer than the server writes SET lines that the server does not know: the single transaction fails.
    version = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True).stdout
    if " 16." not in version:
        pytest.skip(f"needs the PostgreSQL 16 client, found: {version.strip()}")


def _offer(n):
    return {"price_amount": Decimal("10.50") + n, "price_currency": "EUR",
            "legs": [{"mode": "train", "from_name": "Utrecht", "to_name": "Köln",
                      "depart_at": datetime(2026, 12, 1, 8 + n, tzinfo=timezone.utc),
                      "arrive_at": datetime(2026, 12, 1, 11 + n, tzinfo=timezone.utc)}]}


def _counts(engine):
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABLES}


@pytest.fixture
def filled(migrated_url):
    engine = create_engine(migrated_url)
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.commit()
        for price in (0, 1):  # a second capture with a new price adds price history
            body = IngestIn.model_validate({"trip_id": trip.id, "source": "ns", "captured_at": datetime(2026, 11, 6 + price, tzinfo=timezone.utc),
                                            "offers": [_offer(0) | {"price_amount": Decimal("10.50") + price}, _offer(1)]})
            store(s, body)
    yield migrated_url, engine
    engine.dispose()


def test_round_trip_gives_back_all_rows(pg_tools, filled, tmp_path):
    url, engine = filled
    before = _counts(engine)
    assert before["trips"] == 1 and before["itineraries"] >= 2 and before["fare_prices"] >= 3
    dump = backup.dump(url, tmp_path, "manual")
    with engine.begin() as c:
        c.execute(text("TRUNCATE trips CASCADE"))
    assert _counts(engine)["trips"] == 0
    restore.restore(url, dump)
    assert _counts(engine) == before


def test_bad_or_missing_file_exits_1_and_keeps_data(pg_tools, filled, tmp_path, monkeypatch, capsys):
    url, engine = filled
    before = _counts(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    bad = tmp_path / "bad.dump"
    bad.write_text("not a dump")
    for path in (bad, tmp_path / "missing.dump"):
        assert restore.main([str(path)]) == 1
        assert "ERROR: restore failed" in capsys.readouterr().err
        assert _counts(engine) == before
