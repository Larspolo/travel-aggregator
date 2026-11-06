"""The database engine and sessions."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def sqlalchemy_url(url: str) -> str:
    """Use the psycopg 3 driver for a plain postgresql:// URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str | None = None) -> Engine:
    return create_engine(sqlalchemy_url(url or get_settings().database_url), pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


_sessions: sessionmaker[Session] | None = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, from DATABASE_URL (the tests override it)."""
    global _sessions
    if _sessions is None:
        _sessions = make_sessionmaker(make_engine())
    with _sessions() as session:
        yield session
