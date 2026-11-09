"""Conflicts between booked journeys that did not arrive yet (#1653)."""

from datetime import datetime, timedelta, timezone

from app.booked_overlap import Conflict, conflicts
from app.models import Itinerary, Trip

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
ZURICH = timezone(timedelta(minutes=60))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 12, day, hour, minute, tzinfo=ZURICH)


def journey(trip: Trip, depart: datetime, arrive: datetime, booked: bool = True, fingerprint: str = "x") -> Itinerary:
    it = Itinerary(fingerprint=fingerprint, depart_at=depart, arrive_at=arrive,
                   duration_min=int((arrive - depart).total_seconds() // 60), booked=booked)
    trip.itineraries.append(it)
    return it


def test_next_trip_departs_before_outbound_arrives_is_an_order_conflict(sessions):
    with sessions() as s:
        outbound_trip = Trip(title="Outbound", status="planning")
        outbound = journey(outbound_trip, at(1, 10), at(1, 16, 2))
        next_trip = Trip(title="Return", status="planning", return_of=outbound_trip)
        back = journey(next_trip, at(1, 14), at(1, 18))
        s.add_all([outbound_trip, next_trip])
        s.commit()

        result = conflicts(s, NOW)

        assert result == {back.id: [Conflict(outbound.id, outbound_trip.id, "order")]}


def test_order_pair_is_not_also_an_overlap(sessions):
    with sessions() as s:
        outbound_trip = Trip(title="Outbound", status="planning")
        journey(outbound_trip, at(1, 10), at(1, 16, 2))
        next_trip = Trip(title="Return", status="planning", return_of=outbound_trip)
        journey(next_trip, at(1, 14), at(1, 18))
        s.add_all([outbound_trip, next_trip])
        s.commit()

        kinds = [c.kind for cs in conflicts(s, NOW).values() for c in cs]

        assert kinds == ["order"]


def test_unlinked_trips_overlapping_give_an_overlap_on_each(sessions):
    with sessions() as s:
        first_trip = Trip(title="A", status="planning")
        first = journey(first_trip, at(2, 10), at(2, 12))
        second_trip = Trip(title="B", status="planning")
        second = journey(second_trip, at(2, 11), at(2, 13))
        s.add_all([first_trip, second_trip])
        s.commit()

        result = conflicts(s, NOW)

        assert result == {
            first.id: [Conflict(second.id, second_trip.id, "overlap")],
            second.id: [Conflict(first.id, first_trip.id, "overlap")],
        }


def test_touching_journeys_give_no_conflict(sessions):
    with sessions() as s:
        first_trip = Trip(title="A", status="planning")
        journey(first_trip, at(2, 10), at(2, 12))
        second_trip = Trip(title="B", status="planning")
        journey(second_trip, at(2, 12), at(2, 14))
        s.add_all([first_trip, second_trip])
        s.commit()

        assert conflicts(s, NOW) == {}


def test_unbooked_and_arrived_journeys_give_no_conflict(sessions):
    with sessions() as s:
        first_trip = Trip(title="A", status="planning")
        journey(first_trip, at(2, 10), at(2, 12))
        unbooked_trip = Trip(title="B", status="planning")
        journey(unbooked_trip, at(2, 11), at(2, 13), booked=False)
        old_trip = Trip(title="Old", status="planning")
        old = journey(old_trip, at(2, 10, 30), at(2, 11, 30), fingerprint="old")
        s.add_all([first_trip, unbooked_trip, old_trip])
        s.commit()
        # the same journey, but it arrived before "now": it gives no conflict either
        old.depart_at = datetime(2026, 10, 30, 11, tzinfo=timezone.utc)
        old.arrive_at = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
        s.commit()

        assert conflicts(s, NOW) == {}
