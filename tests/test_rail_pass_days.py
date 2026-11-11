"""The travel days and the cost of a rail pass for an itinerary (app/rail_pass.py, #2264). No database."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.rail_pass import pass_cost, pass_days


def leg(mode="train", carrier="DB Fernverkehr AG", depart="2026-12-20T10:00", depart_offset=60,
        arrive="2026-12-20T14:00", arrive_offset=60):
    """A leg with the local times given; the UTC instant is the local time minus the offset (in minutes)."""
    return SimpleNamespace(
        mode=mode,
        carrier=carrier,
        depart_at=_utc(depart, depart_offset),
        depart_offset_min=depart_offset,
        arrive_at=_utc(arrive, arrive_offset),
        arrive_offset_min=arrive_offset,
    )


def _utc(local: str, offset_min: int) -> datetime:
    wall = datetime.fromisoformat(local).replace(tzinfo=timezone.utc)
    return wall - timedelta(minutes=offset_min)


def itinerary(*legs):
    return SimpleNamespace(legs=list(legs))


def rail_pass(carriers="", first="2026-12-01", last="2026-12-31", day_cost="40.00"):
    return SimpleNamespace(
        name="Interrail",
        first_day=date.fromisoformat(first),
        last_day=date.fromisoformat(last),
        day_cost=Decimal(day_cost),
        carriers=carriers,
    )


def test_one_ice_day_costs_one_day():
    trip = itinerary(leg(depart="2026-12-20T08:00", arrive="2026-12-20T13:00", carrier="Deutsche Bahn"))
    assert pass_days(trip, rail_pass()) == 1
    assert pass_cost(trip, rail_pass()) == Decimal("40.00")


def test_night_train_over_midnight_costs_two_days():
    trip = itinerary(leg(depart="2026-12-20T21:00", arrive="2026-12-21T08:00", carrier="Nightjet"))
    assert pass_days(trip, rail_pass(first="2026-12-20", last="2026-12-21")) == 2
    assert pass_cost(trip, rail_pass(first="2026-12-20", last="2026-12-21")) == Decimal("80.00")


def test_departure_before_the_pass_is_not_covered():
    trip = itinerary(leg(depart="2026-11-30T09:00", arrive="2026-11-30T12:00"))
    assert pass_days(trip, rail_pass()) is None
    assert pass_cost(trip, rail_pass()) is None


def test_bus_leg_is_not_covered():
    trip = itinerary(
        leg(depart="2026-12-20T08:00", arrive="2026-12-20T13:00"),
        leg(mode="bus", carrier="FlixBus", depart="2026-12-20T14:00", arrive="2026-12-20T16:00"),
    )
    assert pass_days(trip, rail_pass()) is None


def test_other_carrier_is_not_covered_when_the_pass_names_carriers():
    trip = itinerary(leg(depart="2026-12-20T08:00", arrive="2026-12-20T13:00", carrier="SNCF"))
    assert pass_days(trip, rail_pass(carriers="Deutsche Bahn")) is None


def test_carrier_of_the_pass_matches_the_raw_name_of_the_source():
    trip = itinerary(leg(depart="2026-12-20T08:00", arrive="2026-12-20T13:00", carrier="DB Fernverkehr AG"))
    assert pass_days(trip, rail_pass(carriers="Deutsche Bahn")) == 1


def test_leg_without_carrier_is_not_covered_when_the_pass_names_carriers():
    trip = itinerary(leg(depart="2026-12-20T08:00", arrive="2026-12-20T13:00", carrier=None))
    assert pass_days(trip, rail_pass(carriers="Deutsche Bahn")) is None
    assert pass_days(trip, rail_pass(carriers="")) == 1


def test_departure_in_utc_on_the_day_before_is_local_the_next_day():
    # 23:30 UTC on 2026-11-30 with +60 min is 00:30 local on 2026-12-01: inside the pass.
    trip = itinerary(
        SimpleNamespace(
            mode="train",
            carrier="Deutsche Bahn",
            depart_at=datetime(2026, 11, 30, 23, 30, tzinfo=timezone.utc),
            depart_offset_min=60,
            arrive_at=datetime(2026, 12, 1, 4, 0, tzinfo=timezone.utc),
            arrive_offset_min=60,
        )
    )
    assert pass_days(trip, rail_pass()) == 1
    assert pass_cost(trip, rail_pass()) == Decimal("40.00")


def test_itinerary_without_legs_is_not_covered():
    assert pass_days(itinerary(), rail_pass()) is None
    assert pass_cost(itinerary(), rail_pass()) is None
