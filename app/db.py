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


_sessionmakers: dict[str, sessionmaker[Session]] = {}


def get_db() -> Iterator[Session]:
    """A FastAPI dependency: one session per request, with one engine per database URL."""
    url = get_settings().database_url
    if url not in _sessionmakers:
        _sessionmakers[url] = make_sessionmaker(make_engine(url))
    with _sessionmakers[url]() as session:
        yield session
