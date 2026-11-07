"""The models and the first migration (#4)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Fare, FarePrice, Itinerary, Leg, Trip

TABLES = {"trips", "itineraries", "legs", "fares", "fare_prices", "api_tokens", "captures", "access_times"}


def _alembic(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def migrated(empty_database_url):
    command.upgrade(_alembic(empty_database_url), "head")
    engine = create_engine(empty_database_url)
    yield engine
    engine.dispose()


def _itinerary(trip, fingerprint="abc"):
    t = datetime(2026, 12, 1, 8, 0, tzinfo=timezone(timedelta(hours=1)))
    return Itinerary(trip=trip, fingerprint=fingerprint, depart_at=t, arrive_at=t + timedelta(hours=3), duration_min=180)


def test_upgrade_creates_all_tables(migrated):
    assert TABLES <= set(inspect(migrated).get_table_names())


def test_migration_matches_models(migrated):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    with migrated.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), Base.metadata)
    assert diff == []


def test_duplicate_fingerprint_is_rejected(migrated):
    with Session(migrated) as s:
        trip = Trip(title="Utrecht – Berlin")
        s.add_all([_itinerary(trip), _itinerary(trip)])
        with pytest.raises(IntegrityError):
            s.commit()


def test_money_is_decimal_and_times_keep_utc(migrated):
    with Session(migrated) as s:
        trip = Trip(title="t")
        it = _itinerary(trip)
        local = datetime(2026, 12, 1, 8, 0, tzinfo=timezone(timedelta(hours=1)))
        it.legs.append(Leg(seq=1, mode="train", from_name="A", to_name="B", depart_at=local, depart_offset_min=60,
                           arrive_at=local + timedelta(hours=3), arrive_offset_min=60))
        fare = Fare(source="ns", latest_price=Decimal("19.99"), currency="EUR", latest_captured_at=local, itinerary=it)
        fare.prices.append(FarePrice(price=Decimal("19.99"), currency="EUR", captured_at=local))
        s.add(trip)
        s.commit()
        s.expire_all()
        got = s.get(Fare, fare.id)
        assert got.prices[0].price == Decimal("19.99") and isinstance(got.latest_price, Decimal)
        leg = got.itinerary.legs[0]
        assert leg.depart_at == local and leg.depart_offset_min == 60


def test_downgrade_removes_tables(migrated, empty_database_url):
    command.downgrade(_alembic(empty_database_url), "base")
    assert not TABLES & set(inspect(migrated).get_table_names())
