"""The departed offers (#1391): the trip page ranks only the offers that did not depart yet."""
from datetime import datetime, timezone

from sqlalchemy import or_

from app.models import Itinerary


def clock() -> datetime:
    """The time that separates the departed offers. The tests replace it (tests/conftest.py)."""
    return datetime.now(timezone.utc)


def not_departed(now: datetime):
    """The SQL clause of an itinerary that did not depart at `now`; a booked one stays (the owner travels on it)."""
    return or_(Itinerary.depart_at >= now, Itinerary.booked.is_(True))


def is_departed(it: Itinerary, now: datetime) -> bool:
    return it.depart_at is not None and it.depart_at < now and not it.booked
