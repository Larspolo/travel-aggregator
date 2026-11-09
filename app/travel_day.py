"""The travel-day message of a booked itinerary (#1648): the itineraries that need it, and the mark once sent.

An itinerary is due when it is booked, not yet sent, departs after `now` and at most H hours later, and its trip is
not archived. H = 0 (or no setting) turns the messages off. All times are UTC.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Itinerary, Trip
from app.notify import setting

TRAVEL_DAY_HOURS_KEY = "travel_day_hours"


def _hours(session: Session) -> int:
    try:
        return max(0, int(setting(session, TRAVEL_DAY_HOURS_KEY, "0")))
    except ValueError:
        return 0


def due_travel_days(session: Session, now: datetime) -> list[Itinerary]:
    """The booked itineraries whose travel-day message is due at `now` (timezone-aware), ordered by departure."""
    h = _hours(session)
    if h == 0:
        return []
    now = now.astimezone(timezone.utc)
    query = (
        select(Itinerary)
        .join(Trip, Trip.id == Itinerary.trip_id)
        .where(
            Itinerary.booked.is_(True),
            Itinerary.travel_day_sent_at.is_(None),
            Itinerary.depart_at > now,
            Itinerary.depart_at <= now + timedelta(hours=h),
            Trip.status != "archived",
        )
        .order_by(Itinerary.depart_at, Itinerary.id)
    )
    return list(session.scalars(query))


def mark_sent(itinerary: Itinerary, now: datetime) -> None:
    """Store the time of the travel-day message of `itinerary`; the caller commits."""
    itinerary.travel_day_sent_at = now.astimezone(timezone.utc)
