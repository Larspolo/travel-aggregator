"""The empty fare and leg fields of each source (#1968): `field_health()` counts them in two spans and marks a field
that a source stopped giving."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.field_health import FieldHealth, field_health
from app.models import Fare, Itinerary, Leg, Trip

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
FULL = {"service_no": "ICE 1", "carrier": "DB", "fare_name": "Flex", "travel_class": "2", "flexibility": "flex"}


def _add(sessions, n, days_ago, source="bahn.de", mode="train", extra_leg=None, **empty):
    values = {**FULL, **empty}
    with sessions() as s:
        trip = Trip(title="T", origin_text="A", destination_text="B")
        s.add(trip)
        s.flush()
        at = NOW - timedelta(days=days_ago)
        for i in range(n):
            it = Itinerary(trip_id=trip.id, fingerprint=f"{days_ago}-{i}-{mode}", depart_at=NOW, arrive_at=NOW,
                           duration_min=60)
            it.legs.append(Leg(seq=0, mode=mode, carrier=values["carrier"], service_no=values["service_no"],
                               from_name="A", to_name="B", depart_at=NOW, depart_offset_min=60, arrive_at=NOW,
                               arrive_offset_min=60))
            if extra_leg:
                it.legs.append(Leg(seq=1, mode=extra_leg, from_name="B", to_name="C", depart_at=NOW,
                                   depart_offset_min=60, arrive_at=NOW, arrive_offset_min=60))
            it.fares.append(Fare(source=source, fare_name=values["fare_name"], travel_class=values["travel_class"],
                                 flexibility=values["flexibility"], latest_price=Decimal("10.00"), currency="EUR",
                                 latest_captured_at=at))
            s.add(it)
        s.commit()


def _row(sessions, field, source="bahn.de"):
    with sessions() as s:
        return next(r for r in field_health(s, NOW) if r.source == source and r.field == field)


@pytest.mark.parametrize("field", list(FULL))
def test_a_field_that_a_source_stopped_giving_has_a_mark(sessions, field):
    _add(sessions, 40, 30)
    _add(sessions, 12, 2, **{field: None if field != "flexibility" else " "})
    assert _row(sessions, field) == FieldHealth("bahn.de", field, 12, 12, 0, 40, True)
    assert _row(sessions, "fare_name" if field != "fare_name" else "carrier").empty == 0


def test_a_field_that_was_always_empty_has_no_mark(sessions):
    _add(sessions, 40, 30, service_no=None)
    _add(sessions, 12, 2, service_no=None)
    assert _row(sessions, "service_no") == FieldHealth("bahn.de", "service_no", 12, 12, 40, 40, False)


def test_a_car_leg_does_not_count(sessions):
    _add(sessions, 6, 2, extra_leg="car")
    assert _row(sessions, "service_no").empty == 0
    assert _row(sessions, "carrier").empty == 0


def test_few_recent_fares_give_no_mark(sessions):
    _add(sessions, 40, 30)
    _add(sessions, 2, 2, service_no=None)
    assert _row(sessions, "service_no") == FieldHealth("bahn.de", "service_no", 2, 2, 0, 40, False)


def test_old_fares_and_sources_with_no_recent_fare(sessions):
    _add(sessions, 5, 200, service_no=None)
    _add(sessions, 3, 30, source="trainline")
    with sessions() as s:
        assert field_health(s, NOW) == []
