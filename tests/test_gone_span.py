"""The span of a capture with steady prices (#1404): its fares that it did not show again are gone, and its steady
fares are current."""
import copy
from datetime import datetime, timedelta, timezone

from alembic import command
from sqlalchemy import create_engine, text

from app.gone import gone_fares
from app.ingest import set_span
from app.models import Capture, Fare
from tests.test_ingest_api import BODY
from tests.test_trip_booked import _alembic
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)

T1 = datetime(2026, 11, 3, 19, 41, tzinfo=timezone.utc)
T2 = T1 + timedelta(hours=1)


def _ingest(client, auth, trip_id, at, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, captured_at=at.isoformat(), offers=offers)
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    return r.json()


def _fares(sessions, trip_id):
    with sessions() as s:
        marks = gone_fares(s, [trip_id])
        return {f.fare_name: (f.id in marks, f.latest_captured_at) for f in s.query(Fare).all()}


def test_a_steady_capture_marks_the_fare_that_it_did_not_show(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _ingest(client, auth, tid, T1, [offer("39.00", fare="Sparpreis"), offer("89.00", fare="Flexpreis")])
    counts = _ingest(client, auth, tid, T2, [offer("89.00", fare="Flexpreis")])
    assert counts["unchanged"] == 1
    fares = _fares(sessions, tid)
    assert fares["Sparpreis"] == (True, T1)
    assert fares["Flexpreis"] == (False, T2)  # a steady price is a new capture of the fare (SPEC: staleness)


def test_a_steady_fare_next_to_a_new_price_is_not_gone(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _ingest(client, auth, tid, T1, [offer("39.00", fare="Sparpreis"), offer("89.00", fare="Flexpreis")])
    _ingest(client, auth, tid, T2, [offer("39.00", fare="Sparpreis"), offer("99.00", fare="Flexpreis")])
    fares = _fares(sessions, tid)
    assert fares["Sparpreis"] == (False, T2) and fares["Flexpreis"] == (False, T2)


def test_the_capture_stores_the_span_of_its_offers(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    late = offer("49.00", "ICE 107")
    late["legs"] = copy.deepcopy(late["legs"])
    for leg in late["legs"]:
        for key in ("depart_at", "arrive_at"):
            leg[key] = (datetime.fromisoformat(leg[key]) + timedelta(hours=2)).isoformat()
    _ingest(client, auth, tid, T1, [offer("39.00"), late])
    _ingest(client, auth, tid, T2, [late])
    with sessions() as s:
        spans = [(c.depart_from, c.depart_to) for c in s.query(Capture).order_by(Capture.id)]
    first = datetime.fromisoformat(BODY["offers"][0]["legs"][0]["depart_at"])
    assert spans == [(first, first + timedelta(hours=2)), (first + timedelta(hours=2), first + timedelta(hours=2))]


def test_a_capture_with_no_offer_has_no_span():
    c = Capture(depart_from=T1, depart_to=T2)
    set_span(c, [])
    assert (c.depart_from, c.depart_to) == (None, None)


def test_migration_0029_fills_the_span_from_the_price_rows(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0028")
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO trips (id, title) VALUES (1, 't')"))
            c.execute(text("INSERT INTO captures (id, trip_id, source, captured_at) VALUES "
                           "(1, 1, 'bahn.de', '2026-11-03 19:41+00'), (2, 1, 'bahn.de', '2026-11-03 20:41+00')"))
            for i, hour in ((1, 8), (2, 10)):
                c.execute(text("INSERT INTO itineraries (id, trip_id, fingerprint, depart_at, arrive_at, duration_min, "
                               f"transfers) VALUES ({i}, 1, 'f{i}', '2026-12-20 {hour}:00+00', '2026-12-20 {hour + 2}:00+00', 120, 0)"))
                c.execute(text("INSERT INTO fares (id, itinerary_id, source, latest_price, currency, latest_captured_at) "
                               f"VALUES ({i}, {i}, 'bahn.de', 10, 'EUR', '2026-11-03 19:41+00')"))
                c.execute(text("INSERT INTO fare_prices (fare_id, price, currency, captured_at, capture_id) "
                               f"VALUES ({i}, 10, 'EUR', '2026-11-03 19:41+00', 1)"))
        command.upgrade(cfg, "0029")
        with engine.connect() as c:
            rows = c.execute(text("SELECT id, extract(hour FROM depart_from AT TIME ZONE 'UTC'), "
                                  "extract(hour FROM depart_to AT TIME ZONE 'UTC') FROM captures ORDER BY id")).all()
        assert [tuple(None if v is None else int(v) for v in r) for r in rows] == [(1, 8, 10), (2, None, None)]
        command.downgrade(cfg, "0028")
        command.upgrade(cfg, "0029")
    finally:
        engine.dispose()
