"""The secret link of the calendar feed of all booked journeys (#1112): the database holds only the hash (P5)."""

import hmac
import secrets

from sqlalchemy.orm import Session

from app.auth import hash_token
from app.models import Setting

KEY = "calendar_feed_hash"


def new_feed_token(session: Session) -> str:
    """Give a new feed token. It replaces the last token: the old link stops."""
    token = secrets.token_urlsafe(32)
    setting = session.get(Setting, KEY)
    if setting is None:
        session.add(Setting(key=KEY, value=hash_token(token)))
    else:
        setting.value = hash_token(token)
    return token


def revoke_feed(session: Session) -> None:
    setting = session.get(Setting, KEY)
    if setting is not None:
        session.delete(setting)


def feed_token_ok(session: Session, token: str) -> bool:
    """True if the token is the feed token. The hash is compared in constant time."""
    setting = session.get(Setting, KEY)
    if setting is None or not setting.value:
        return False
    return hmac.compare_digest(setting.value.encode(), hash_token(token).encode())
