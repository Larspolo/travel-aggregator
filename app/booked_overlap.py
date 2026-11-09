"""Conflicts between the booked journeys that did not arrive yet (#1653), for the Upcoming page and the trip page (#1652).

Two kinds of conflict:
- "overlap": two booked journeys (of any trips) are in time at the same moment.
- "order": a booked journey of a trip departs before a booked journey of the trip before it (`return_of_id`) arrives.
  The conflict is on the journey of the later trip. A pair of journeys with "order" is not also "overlap".
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Itinerary, Trip


@dataclass(frozen=True)
class Conflict:
    other_id: int  # the other itinerary
    other_trip_id: int  # the trip of the other itinerary
    kind: str  # "overlap" or "order"


def conflicts(session: Session, now: datetime) -> dict[int, list[Conflict]]:
    """The conflicts per itinerary id; an itinerary without a conflict has no key."""
    rows = list(session.scalars(
        select(Itinerary).where(Itinerary.booked.is_(True), Itinerary.arrive_at >= now)
        .order_by(Itinerary.depart_at, Itinerary.id)
    ).all())
    # the trip before each trip: later trip id -> earlier trip id
    previous = dict(session.execute(
        select(Trip.id, Trip.return_of_id).where(Trip.return_of_id.is_not(None))
    ).all())

    result: dict[int, list[Conflict]] = {}
    ordered: set[frozenset[int]] = set()
    for later in rows:
        for earlier in rows:
            if later.id == earlier.id or previous.get(later.trip_id) != earlier.trip_id:
                continue
            if later.depart_at < earlier.arrive_at:
                result.setdefault(later.id, []).append(Conflict(earlier.id, earlier.trip_id, "order"))
                ordered.add(frozenset((earlier.id, later.id)))

    for i, first in enumerate(rows):
        for second in rows[i + 1:]:
            if frozenset((first.id, second.id)) in ordered:
                continue
            if first.depart_at < second.arrive_at and second.depart_at < first.arrive_at:
                result.setdefault(first.id, []).append(Conflict(second.id, second.trip_id, "overlap"))
                result.setdefault(second.id, []).append(Conflict(first.id, first.trip_id, "overlap"))
    return result
