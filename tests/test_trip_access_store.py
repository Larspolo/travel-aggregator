"""The access places of a trip and the merge with the global places (#2108)."""

from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.door import trip_places
from app.models import AccessTime, Trip, TripAccessTime


def _setup(s):
    a, b = Trip(title="A"), Trip(title="B")
    s.add_all([a, b, AccessTime(place_text="Zürich HB", kind="egress", minutes=20, cost=Decimal("0"))])
    s.flush()
    s.add(TripAccessTime(trip_id=a.id, place_text="zürich hb ", kind="egress", minutes=10, cost=Decimal("2.50")))
    s.commit()
    return a, b


def test_override_replaces_global_for_its_trip_only(sessions):
    with sessions() as s:
        a, b = _setup(s)
        places_a = [p for p in trip_places(s, a) if p.kind == "egress"]
        assert [(p.minutes, getattr(p, "trip", False)) for p in places_a] == [(10, True)]
        places_b = trip_places(s, b)
        assert [(p.minutes, getattr(p, "trip", False)) for p in places_b] == [(20, False)]


def test_duplicate_override_fails_and_trip_delete_cascades(sessions):
    with sessions() as s:
        a, _ = _setup(s)
        s.add(TripAccessTime(trip_id=a.id, place_text=" ZÜRICH HB", kind="egress", minutes=5, cost=Decimal("0")))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        s.delete(s.get(Trip, a.id))
        s.commit()
        assert s.query(TripAccessTime).count() == 0


def test_migration_up_and_down(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0052")
    command.downgrade(cfg, "0051")
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as conn:
            assert conn.execute(text("SELECT to_regclass('trip_access_times')")).scalar() is None
    finally:
        engine.dispose()
    command.upgrade(cfg, "0052")
