"""The database engine and sessions."""

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
