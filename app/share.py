"""The secret share link of a trip (#903): the database holds only the hash of the token (P5)."""

import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_token
from app.models import Trip


def new_link(trip: Trip) -> str:
    """Give a new token for the trip. It replaces the last token: the old link stops."""
    token = secrets.token_urlsafe(32)
    trip.share_hash = hash_token(token)
    trip.shared_at = datetime.now(timezone.utc)
    return token


def revoke(trip: Trip) -> None:
    trip.share_hash = None
    trip.shared_at = None


def trip_for_token(session: Session, token: str) -> Trip | None:
    """The trip of a share token, else None. The hash is compared in constant time, as `require_token()` does."""
    digest = hash_token(token)
    trip = session.scalars(select(Trip).where(Trip.share_hash == digest)).one_or_none()
    if trip is None or not hmac.compare_digest(trip.share_hash.encode(), digest.encode()):
        return None
    return trip
