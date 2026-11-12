"""A bahn.de connection with the cancel notice marks its stored itinerary as cancelled by the operator (#2629)."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, inspect, select

from app import ingest
from app.models import Itinerary, Trip
from app.parsers.bahn import BahnParser
from app.schemas import IngestIn, OfferIn

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"
T1, T2, T3 = (datetime(2026, 5, 1, h, tzinfo=UTC) for h in (8, 9, 10))


def raw():
    return json.loads(FIX.read_text(encoding="utf-8"))


def cancelled_legs():
    return BahnParser().parse(raw()).cancelled[0]


def offer():
    return OfferIn(price_amount=Decimal("50.00"), price_currency="EUR", fare_name="Flex", legs=cancelled_legs())


def trip(s):
    t = Trip(title="Köln – München")
    s.add(t)
    s.commit()
    return t.id


def marks(s, trip_id):
    return [it.operator_cancelled_at for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))]


def test_the_fixture_gives_one_cancelled_connection_and_no_error():
    r = BahnParser().parse(raw())
    assert r.errors == []
    assert [[(x.service_no, x.from_name, x.to_name) for x in c] for c in r.cancelled] == [
        [("S6", "Köln Hbf", "Köln Messe/Deutz"), ("ICE 611", "Köln Messe/Deutz Gl.11-12", "München Hbf")]]


def test_a_capture_marks_and_a_newer_offer_clears(sessions):
    with sessions() as s:
        tid = trip(s)
        ingest.upsert_offers(s, tid, None, [offer()], source="bahn.de", captured_at=T1)
        answer = ingest.store(s, IngestIn(trip_id=tid, source="bahn.de", captured_at=T2, raw=raw()))
        assert answer["rejected"] == 0
        s.expire_all()
        cancelled = [m for m in marks(s, tid) if m is not None]
        assert cancelled == [T2]
        ingest.upsert_offers(s, tid, None, [offer()], source="bahn.de", captured_at=T3)
        s.expire_all()
        assert all(m is None for m in marks(s, tid))


def test_a_cancelled_connection_with_no_itinerary_makes_no_row(sessions):
    with sessions() as s:
        tid = trip(s)
        ingest.mark_cancelled(s, tid, [cancelled_legs()], T2)
        s.commit()
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == tid)) == 0


def test_the_migration_upgrades_and_downgrades_to_0071(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)

    def cols():
        return {c["name"] for c in inspect(engine).get_columns("itineraries")}
    try:
        assert "operator_cancelled_at" in cols()
        command.downgrade(cfg, "0071")
        assert "operator_cancelled_at" not in cols()
        command.upgrade(cfg, "head")
        assert "operator_cancelled_at" in cols()
    finally:
        engine.dispose()
