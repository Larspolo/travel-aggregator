"""Delete a capture and the offers that only it gave (#2186): app/capture_delete.py."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app import ingest
from app.capture_delete import delete_capture, delete_counts
from app.models import Capture, DayPrice, Fare, FarePrice, Itinerary, Trip
from app.schemas import IngestIn


def _offer(no, hour, price):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Flex",
            "legs": [{"mode": "train", "carrier": "DB", "service_no": no, "from_name": "Amsterdam",
                      "to_name": "Zürich", "depart_at": f"2026-12-01T{hour:02}:00:00+01:00",
                      "arrive_at": f"2026-12-01T{hour + 3:02}:00:00+01:00"}]}


def _setup(s, offers_a, offers_b):
    trip = Trip(title="T", origin_text="Amsterdam", destination_text="Zürich")
    s.add(trip)
    s.commit()
    caps = []
    for day, offers in ((1, offers_a), (2, offers_b)):
        ingest.store(s, IngestIn.model_validate({
            "trip_id": trip.id, "source": "stub", "captured_at": datetime(2026, 11, day, 10, tzinfo=UTC),
            "offers": offers}))
        caps.append(s.scalars(select(Capture).order_by(Capture.id.desc())).first())
    return trip.id, caps[0], caps[1]


def _fare(s, no):
    for it in s.scalars(select(Itinerary)):
        if it.legs[0].service_no == no:
            return it.fares[0]
    return None


def test_the_delete_of_b_gives_back_the_price_of_a(sessions):
    with sessions() as s:
        trip, a, b = _setup(s, [_offer("ICE 105", 8, "89")], [_offer("ICE 105", 8, "79"), _offer("IC 2021", 9, "45")])
        s.add(DayPrice(trip_id=trip, capture_id=b.id, **_day_kwargs()))
        s.commit()
        before = delete_counts(s, b)
        assert delete_capture(s, b) == before == {"prices": 2, "fares": 1, "itineraries": 1, "day_prices": 1}
        s.commit()
        fare = _fare(s, "ICE 105")
        assert fare.latest_price == Decimal("89") and len(fare.prices) == 1
        assert fare.latest_captured_at == datetime(2026, 11, 1, 10, tzinfo=UTC)
        assert _fare(s, "IC 2021") is None
        assert s.get(Capture, b.id) is None
        assert s.scalar(select(func.count()).select_from(DayPrice)) == 0


def _day_kwargs():
    cols = {c.name for c in DayPrice.__table__.columns}
    kw = {"day": datetime(2026, 12, 1).date(), "price": Decimal("45"), "currency": "EUR", "source": "stub", "captured_at": datetime(2026, 11, 2, 10, tzinfo=UTC)}
    return {k: v for k, v in kw.items() if k in cols}


def test_a_marked_journey_of_only_b_stays_with_its_last_price(sessions):
    with sessions() as s:
        _, _, b = _setup(s, [_offer("ICE 105", 8, "89")],
                         [_offer("IC 1", 9, "45"), _offer("IC 2", 10, "46"), _offer("IC 3", 11, "47")])
        _fare(s, "IC 1").itinerary.booked = True
        _fare(s, "IC 2").itinerary.pinned = True
        _fare(s, "IC 3").itinerary.note = "x"
        s.commit()
        assert delete_counts(s, b)["itineraries"] == 0
        delete_capture(s, b)
        s.commit()
        for no, price in (("IC 1", "45"), ("IC 2", "46"), ("IC 3", "47")):
            fare = _fare(s, no)
            assert fare.latest_price == Decimal(price)
            assert [p.capture_id for p in fare.prices] == [None]


def test_a_fare_seen_again_by_b_at_the_same_price_stays_after_the_delete_of_a(sessions):
    with sessions() as s:
        _, a, _ = _setup(s, [_offer("ICE 105", 8, "89")], [_offer("ICE 105", 8, "89")])
        assert delete_counts(s, a) == {"prices": 0, "fares": 0, "itineraries": 0, "day_prices": 0}
        delete_capture(s, a)
        s.commit()
        fare = _fare(s, "ICE 105")
        assert fare.latest_price == Decimal("89")
        assert fare.latest_captured_at == datetime(2026, 11, 2, 10, tzinfo=UTC)
        assert s.scalar(select(func.count()).select_from(FarePrice)) == 1
        assert s.scalar(select(func.count()).select_from(Fare)) == 1
