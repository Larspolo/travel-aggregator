"""Retention of the raw captures: each ingest deletes the captures older than the retention period. The offers and
their price rows stay; a price row of a deleted capture keeps its row with `capture_id` NULL (FK ON DELETE SET NULL)."""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Capture, Setting

RETENTION_DAYS = 90
RETENTION_KEY = "capture_retention_days"
MAX_RETENTION_DAYS = 3650


def retention_days(session: Session) -> int:
    """The retention period of the settings page (#207), else `RETENTION_DAYS`."""
    row = session.get(Setting, RETENTION_KEY)
    try:
        return int(row.value) if row is not None else RETENTION_DAYS
    except ValueError:
        return RETENTION_DAYS


def delete_old_captures(session: Session, days: int, now: datetime) -> int:
    """Delete the captures captured before `now - days`. Returns the number of deleted rows. `days == 0` deletes
    nothing. The caller commits."""
    if days == 0:
        return 0
    result = session.execute(delete(Capture).where(Capture.captured_at < now - timedelta(days=days)))
    return result.rowcount
