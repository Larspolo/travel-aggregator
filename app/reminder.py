"""The trips that need a new search (#1118): the reminder sender only formats and sends them.

A trip is due when it is not archived, has a pinned itinerary or a target price, departs today or at most D days
later, its newest capture is older than N days (or it has none), and its last reminder is older than N days (or
it has none). N = 0 turns the reminders off. All times are UTC.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import Capture, Itinerary, Trip
from app.notify import REMINDER_BEFORE_KEY, REMINDER_DAYS_KEY, setting


def _days(session: Session, key: str, default: str) -> int:
    try:
        return max(0, int(setting(session, key, default)))
    except ValueError:
        return int(default)


def due_reminders(session: Session, now: datetime) -> list[Trip]:
    """The trips that need a reminder at `now` (timezone-aware), ordered by departure."""
    n = _days(session, REMINDER_DAYS_KEY, "0")
    d = _days(session, REMINDER_BEFORE_KEY, "14")
    if n == 0:
        return []
    now = now.astimezone(timezone.utc)
    today = now.date()
    cutoff = now - timedelta(days=n)
    pinned = exists().where(Itinerary.trip_id == Trip.id, Itinerary.pinned.is_(True))
    newest = select(func.max(Capture.captured_at)).where(Capture.trip_id == Trip.id).scalar_subquery()
    query = select(Trip).where(
        Trip.status != "archived",
        or_(pinned, Trip.target_price.is_not(None)),
        Trip.date_from >= today, Trip.date_from <= today + timedelta(days=d),
        or_(newest.is_(None), newest < cutoff),
        or_(Trip.reminded_at.is_(None), Trip.reminded_at < cutoff),
    ).order_by(Trip.date_from, Trip.id)
    return list(session.scalars(query))


def mark_reminded(trip: Trip, now: datetime) -> None:
    """Store the time of the reminder of `trip`; the caller commits."""
    trip.reminded_at = now.astimezone(timezone.utc)
