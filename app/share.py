"""The secret share link of a trip (#903): the database holds only the hash of the token (P5)."""

import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, object_session

from app.auth import hash_token
from app.models import ShareMark, Trip


def _delete_marks(trip: Trip) -> None:
    """Delete the "Suits me" marks of the trip (#1781): they belong to the link that stops."""
    session = object_session(trip)
    if session is not None and trip.id is not None:
        session.execute(delete(ShareMark).where(ShareMark.trip_id == trip.id))


def new_link(trip: Trip) -> str:
    """Give a new token for the trip. It replaces the last token: the old link and its marks stop."""
    _delete_marks(trip)
    token = secrets.token_urlsafe(32)
    trip.share_hash = hash_token(token)
    trip.shared_at = datetime.now(timezone.utc)
    return token


def revoke(trip: Trip) -> None:
    """Stop the link of the trip and delete its marks."""
    _delete_marks(trip)
    trip.share_hash = None
    trip.shared_at = None


def trip_for_token(session: Session, token: str) -> Trip | None:
    """The trip of a share token, else None. The hash is compared in constant time, as `require_token()` does."""
    digest = hash_token(token)
    trip = session.scalars(select(Trip).where(Trip.share_hash == digest)).one_or_none()
    if trip is None or not hmac.compare_digest(trip.share_hash.encode(), digest.encode()):
        return None
    return trip
