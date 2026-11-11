"""The other trips in planning of the same journey as a trip, for the duplicate warning (#1591)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Trip
from app.place_names import aliases
from app.route_history import _same_place


def _span(trip: Trip) -> tuple[date, date] | None:
    """The first and last day of a trip; the last day is the first day when there is no end date."""
    if trip.date_from is None:
        return None
    return trip.date_from, trip.date_to or trip.date_from


def duplicate_trips(session: Session, trip: Trip) -> list[Trip]:
    """The other trips in planning on the same route whose dates share a day with the trip, by id."""
    if trip.status != "planning" or trip.split_of_id is not None:
        return []
    span = _span(trip)
    if span is None:
        return []
    start, end = span
    found = []
    names = aliases(session)
    for other in session.scalars(select(Trip).where(Trip.id != trip.id, Trip.status == "planning",
                                                    Trip.split_of_id.is_(None)).order_by(Trip.id)):
        other_span = _span(other)
        if other_span is None or not (other_span[0] <= end and start <= other_span[1]):
            continue
        if (_same_place(other.origin_text, trip.origin_text, names)
                    and _same_place(other.destination_text, trip.destination_text, names)):
            found.append(other)
    return found
