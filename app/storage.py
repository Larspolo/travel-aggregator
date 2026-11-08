"""The storage use of the database and of the raw captures, for the settings page (#1235)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Capture
from app.retention import cutoff


@dataclass(frozen=True)
class SourceUse:
    source: str
    captures: int
    raw_bytes: int


@dataclass(frozen=True)
class StorageUse:
    database_bytes: int
    sources: list[SourceUse]
    captures: int
    raw_bytes: int
    cleanup_captures: int
    cleanup_bytes: int


def _raw_size():
    return func.coalesce(func.sum(func.octet_length(Capture.raw_gz)), 0)


def storage_use(session: Session, days: int, now: datetime) -> StorageUse:
    """The database size, the captures per source and the captures that the next cleanup deletes (in bytes)."""
    database_bytes = int(session.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    rows = session.execute(
        select(Capture.source, func.count(Capture.id), _raw_size()).group_by(Capture.source)).all()
    sources = sorted((SourceUse(r[0], int(r[1]), int(r[2])) for r in rows), key=lambda u: (-u.raw_bytes, u.source))
    cleanup_captures = cleanup_bytes = 0
    limit = cutoff(days, now)
    if limit is not None:
        count, size = session.execute(
            select(func.count(Capture.id), _raw_size()).where(Capture.captured_at < limit)).one()
        cleanup_captures, cleanup_bytes = int(count), int(size)
    return StorageUse(database_bytes=database_bytes, sources=sources,
                      captures=sum(u.captures for u in sources), raw_bytes=sum(u.raw_bytes for u in sources),
                      cleanup_captures=cleanup_captures, cleanup_bytes=cleanup_bytes)
