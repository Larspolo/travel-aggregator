"""One itinerary for one journey from bahn.de and NS International (#484, epic #481): the journey key as fingerprint,
the real legs of bahn.de, and the migration 0014 that merges the stored itineraries of one journey."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from app import tokens
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip
from app.parsers.ns import CHANGE_STATION

DEP, CHG_ARR, CHG_DEP, ARR = ("2026-12-20T07:00:00+01:00", "2026-12-20T11:00:00+01:00",
                              "2026-12-20T11:20:00+01:00", "2026-12-20T14:00:00+01:00")


def _bahn(depart_at=DEP):
    return {"source": "bahn.de", "offers": [{
        "price_amount": "89.90", "price_currency": "EUR", "fare_name": "Sparpreis",
        "legs": [
            {"mode": "train", "carrier": "DB Fernverkehr AG", "service_no": "ICE 121", "from_name": "Amsterdam Centraal",
             "to_name": "Frankfurt(Main)Hbf", "depart_at": depart_at, "arrive_at": CHG_ARR},
            {"mode": "train", "carrier": "DB Fernverkehr AG", "service_no": "ICE 571", "from_name": "Frankfurt(Main)Hbf",
             "to_name": "Basel SBB", "depart_at": CHG_DEP, "arrive_at": ARR},
        ]}]}


def _ns():
    """The NS form (app/parsers/ns.py): no carrier; only the journey start and end are real."""
    return {"source": "nsinternational.com", "offers": [{
        "price_amount": "79.00", "price_currency": "EUR", "fare_name": "Saver",
        "legs": [
            {"mode": "train", "carrier": None, "service_no": "ICE121", "from_name": "Amsterdam Centraal",
             "to_name": CHANGE_STATION, "depart_at": DEP, "arrive_at": DEP},
            {"mode": "train", "carrier": None, "service_no": "ice 571", "from_name": CHANGE_STATION,
             "to_name": "Basel SBB", "depart_at": DEP, "arrive_at": ARR},
        ]}]}


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Basel")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}

    def post(payload):
        body = {"trip_id": trip_id, "parser_version": "1", "captured_at": "2026-11-07T10:00:00Z", **payload}
        r = client.post("/api/ingest", json=body, headers=auth)
        assert r.status_code == 200, r.text
        return r.json()
    return post


@pytest.mark.parametrize("order", [(_bahn, _ns), (_ns, _bahn)], ids=["bahn first", "ns first"])
def test_one_journey_from_two_sources_is_one_itinerary_with_the_real_legs(setup, sessions, order):
    for make in order:
        setup(make())
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 1
        assert sorted(s.scalars(select(Fare.source)).all()) == ["bahn.de", "nsinternational.com"]
        legs = s.scalars(select(Leg).order_by(Leg.seq)).all()
        assert [(leg.from_name, leg.to_name, leg.carrier) for leg in legs] == [
            ("Amsterdam Centraal", "Frankfurt(Main)Hbf", "DB Fernverkehr AG"),
            ("Frankfurt(Main)Hbf", "Basel SBB", "DB Fernverkehr AG")]
        it = s.scalar(select(Itinerary))
        assert (it.transfers, it.duration_min) == (1, 420)


def test_the_same_trains_with_another_first_departure_stay_two_itineraries(setup, sessions):
    setup(_bahn())
    setup(_bahn(depart_at="2026-12-20T07:05:00+01:00"))
    setup(_ns())
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 2
        assert s.scalar(select(func.count()).select_from(Fare)) == 3


# The migration 0014: rows in the form of revision 0013, then the upgrade.

def _alembic(url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


T = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def _insert_itinerary(c, trip, fp, legs, *, pinned=False, hidden=False, note=None, seen=T):
    it = c.execute(text(
        "INSERT INTO itineraries (trip_id, fingerprint, mode_summary, depart_at, arrive_at, duration_min, transfers, "
        "first_seen_at, last_seen_at, hidden, pinned, booked, note) VALUES (:t, :fp, 'train', :d, :a, 420, 1, :s, :s, "
        ":h, :p, false, :n) RETURNING id"),
        {"t": trip, "fp": fp, "d": DEP, "a": ARR, "s": seen, "h": hidden, "p": pinned, "n": note}).scalar()
    for seq, (carrier, service, frm, to, dep, arr) in enumerate(legs, 1):
        c.execute(text("INSERT INTO legs (itinerary_id, seq, mode, carrier, service_no, from_name, to_name, depart_at, "
                       "depart_offset_min, arrive_at, arrive_offset_min) VALUES (:i, :q, 'train', :c, :sn, :f, :to, "
                       ":d, 60, :a, 60)"),
                  {"i": it, "q": seq, "c": carrier, "sn": service, "f": frm, "to": to, "d": dep, "a": arr})
    return it


def _insert_fare(c, it, source, name, price, at):
    fare = c.execute(text("INSERT INTO fares (itinerary_id, source, fare_name, latest_price, currency, "
                          "latest_captured_at) VALUES (:i, :s, :n, :p, 'EUR', :at) RETURNING id"),
                     {"i": it, "s": source, "n": name, "p": price, "at": at}).scalar()
    c.execute(text("INSERT INTO fare_prices (fare_id, price, currency, captured_at) VALUES (:f, :p, 'EUR', :at)"),
              {"f": fare, "p": price, "at": at})
    return fare


BAHN_LEGS = [("DB Fernverkehr AG", "ICE 121", "Amsterdam Centraal", "Frankfurt(Main)Hbf", DEP, CHG_ARR),
             ("DB Fernverkehr AG", "ICE 571", "Frankfurt(Main)Hbf", "Basel SBB", CHG_DEP, ARR)]
NS_LEGS = [(None, "ICE 121", "Amsterdam Centraal", CHANGE_STATION, DEP, DEP),
           (None, "ICE 571", CHANGE_STATION, "Basel SBB", DEP, ARR)]


def test_the_migration_merges_the_stored_itineraries_of_one_journey(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0013")
    engine = create_engine(empty_database_url)
    later = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    with engine.begin() as c:
        trip = c.execute(text("INSERT INTO trips (title, status) VALUES ('t', 'planning') RETURNING id")).scalar()
        other = c.execute(text("INSERT INTO trips (title, status) VALUES ('u', 'planning') RETURNING id")).scalar()
        ns = _insert_itinerary(c, trip, "old-ns", NS_LEGS, note="window seat")
        bahn = _insert_itinerary(c, trip, "old-bahn", BAHN_LEGS, pinned=True, note="  ")
        bahn2 = _insert_itinerary(c, trip, "old-bahn-2", [("Nederlandse Spoorwegen", *BAHN_LEGS[0][1:]),
                                                          BAHN_LEGS[1]], hidden=True, seen=later)
        alone = _insert_itinerary(c, other, "old-other", BAHN_LEGS)  # the same journey in another trip stays
        _insert_fare(c, ns, "nsinternational.com", "Saver", "79.00", T)
        _insert_fare(c, bahn, "bahn.de", "Sparpreis", "89.90", T)
        _insert_fare(c, bahn2, "bahn.de", "Sparpreis", "84.90", later)  # the same fare: one fare, two prices
        _insert_fare(c, alone, "bahn.de", "Sparpreis", "99.00", T)
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, trip_id, pinned, hidden, note, last_seen_at, fingerprint FROM itineraries "
                              "ORDER BY id")).all()
        assert [(r.id, r.trip_id) for r in rows] == [(ns, trip), (alone, other)]
        kept = rows[0]
        assert (kept.pinned, kept.hidden, kept.note, kept.last_seen_at) == (True, False, "window seat", later)
        assert rows[0].fingerprint == rows[1].fingerprint  # the same journey key; the trips differ
        legs = c.execute(text("SELECT from_name, carrier FROM legs WHERE itinerary_id = :i ORDER BY seq"),
                         {"i": ns}).all()
        assert [tuple(r) for r in legs] == [("Amsterdam Centraal", "DB Fernverkehr AG"),
                                            ("Frankfurt(Main)Hbf", "DB Fernverkehr AG")]
        fares = c.execute(text("SELECT id, source, latest_price FROM fares WHERE itinerary_id = :i ORDER BY source"),
                          {"i": ns}).all()
        assert [(f.source, f.latest_price) for f in fares] == [("bahn.de", Decimal("84.90")),
                                                                ("nsinternational.com", Decimal("79.00"))]
        prices = c.execute(text("SELECT price FROM fare_prices WHERE fare_id = :f ORDER BY price"),
                           {"f": fares[0].id}).scalars().all()
        assert prices == [Decimal("84.90"), Decimal("89.90")]
    command.downgrade(cfg, "-1")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM itineraries")).scalar() == 2
    command.upgrade(cfg, "head")
    engine.dispose()

