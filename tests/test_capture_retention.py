"""The captures older than the retention period are deleted at each ingest; their offers and prices stay (#206)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ingest import store, upsert_offers
from app.models import Capture, FarePrice, Trip
from app.retention import delete_old_captures
from app.schemas import IngestIn, LegIn, OfferIn

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


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


def _offer(depart: datetime, price: str) -> OfferIn:
    leg = LegIn(mode="train", carrier="NS", service_no="IC 1", from_name="Utrecht", to_name="Amsterdam",
                depart_at=depart, arrive_at=depart + timedelta(minutes=30))
    return OfferIn(price_amount=Decimal(price), price_currency="EUR", fare_name="Enkele reis", legs=[leg])


def _capture(session: Session, trip_id: int, captured_at: datetime) -> Capture:
    cap = Capture(trip_id=trip_id, source="ns", captured_at=captured_at, raw_gz=None)
    session.add(cap)
    session.flush()
    return cap


def test_capture_91_days_old_is_deleted_and_89_days_old_stays(engine):
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        old = _capture(s, trip.id, NOW - timedelta(days=91))
        recent = _capture(s, trip.id, NOW - timedelta(days=89))
        s.commit()
        old_id, recent_id = old.id, recent.id
    with Session(engine) as s:
        assert delete_old_captures(s, 90, NOW) == 1
        s.commit()
    with Session(engine) as s:
        assert s.get(Capture, old_id) is None
        assert s.get(Capture, recent_id) is not None


def test_ingest_deletes_old_capture_and_keeps_fare_prices(engine):
    depart = NOW + timedelta(days=3)
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        old = _capture(s, trip.id, NOW - timedelta(days=91))
        upsert_offers(s, trip.id, old.id, [_offer(depart, "12.30")], source="ns",
                      captured_at=NOW - timedelta(days=91))
        old_id, trip_id = old.id, trip.id
    with Session(engine) as s:
        body = IngestIn.model_construct(trip_id=trip_id, source="ns", parser_version="1", captured_at=NOW,
                                        page_url=None, search_context=None, raw=None, offers=[])
        store(s, body)
    with Session(engine) as s:
        assert s.get(Capture, old_id) is None
        prices = s.scalars(select(FarePrice)).all()
        assert len(prices) == 1
        assert prices[0].capture_id is None
        assert prices[0].price == Decimal("12.30")


def test_zero_days_deletes_nothing(engine):
    with Session(engine) as s:
        trip = Trip(title="T")
        s.add(trip)
        s.flush()
        _capture(s, trip.id, NOW - timedelta(days=400))
        s.commit()
    with Session(engine) as s:
        assert delete_old_captures(s, 0, NOW) == 0
        s.commit()
    with Session(engine) as s:
        assert len(s.scalars(select(Capture)).all()) == 1
