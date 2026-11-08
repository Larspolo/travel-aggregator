"""A daily dump of app.backup restores with app.restore to the same rows (criterion 4 of epic #545)."""

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
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
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + os.environ["PATH"])
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


def _prices(engine):
    with engine.connect() as c:
        return sorted(c.execute(text("SELECT price FROM fare_prices")).scalars().all())


@pytest.fixture
def filled(migrated_url):
    engine = create_engine(migrated_url)
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.commit()
        for price in (0, 1):  # a second capture with a new price adds price history
            body = IngestIn.model_validate({"trip_id": trip.id, "source": "ns",
                                            "captured_at": datetime(2026, 11, 6 + price, tzinfo=timezone.utc),
                                            "offers": [_offer(0) | {"price_amount": Decimal("10.50") + price},
                                                       _offer(1)]})
            store(s, body)
    yield migrated_url, engine
    engine.dispose()


def test_a_daily_dump_restores_the_trips_offers_and_price_history(pg_tools, filled, tmp_path):
    url, engine = filled
    before, prices_before = _counts(engine), _prices(engine)
    assert before["trips"] == 1 and before["itineraries"] >= 2 and before["fare_prices"] >= 3
    backup.daily_step(url, tmp_path, timedelta(hours=24), now=datetime(2026, 11, 8, 12, tzinfo=timezone.utc))
    dumps = sorted(tmp_path.glob("*-daily.dump"))
    assert len(dumps) == 1
    with engine.begin() as c:
        c.execute(text("TRUNCATE trips CASCADE"))
    assert _counts(engine)["trips"] == 0
    restore.restore(url, dumps[0])
    assert _counts(engine) == before
    assert _prices(engine) == prices_before
