"""The bicycle part of a reservation fare on a trip with a rail pass that covers it (#2512, epic #2472)."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary, RailPass, Trip
from app.ranking import Weights, format_breakdown
from app.web.pages import row_cost
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

STALE = datetime(2000, 1, 1, tzinfo=timezone.utc)
WEIGHTS = Weights(bike_fee=Decimal("9"))


def _setup(sessions, trip_id, bike):
    with sessions() as s:
        rp = RailPass(name="Interrail", first_day=date(2026, 12, 1), last_day=date(2026, 12, 31),
                      day_cost=Decimal("40.00"), carriers="", updated_at=datetime.now(timezone.utc))
        s.add(rp)
        s.flush()
        t = s.get(Trip, trip_id)
        t.rail_pass_id = rp.id
        t.bike = bike
        for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)):
            for f in it.fares:
                if f.latest_price == Decimal("139.90"):
                    f.bike = "reservation"
        s.commit()


def _ice_breakdown(sessions, trip_id):
    with sessions() as s:
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).one()
        assert len(it.legs) == 2
        fare, b = row_cost(it, it.fares, [], WEIGHTS, STALE, {})
        assert fare.latest_price == Decimal("139.90")
        return b


def test_a_bicycle_reservation_under_a_covering_pass_adds_the_bicycle_part(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("139.90", "ICE 105")])
    _setup(sessions, trip_id, bike=True)
    b = _ice_breakdown(sessions, trip_id)
    assert ("pass Interrail", Decimal("40.00")) in b.extras
    assert ("bicycle", Decimal("18")) in b.extras
    assert b.price == 0
    assert "€18 bicycle" in format_breakdown(b)


def test_a_trip_without_bicycle_under_a_covering_pass_has_no_bicycle_part(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("139.90", "ICE 105")])
    _setup(sessions, trip_id, bike=False)
    b = _ice_breakdown(sessions, trip_id)
    assert ("pass Interrail", Decimal("40.00")) in b.extras
    assert not any(label == "bicycle" for label, _ in b.extras)
    assert "bicycle" not in format_breakdown(b)
