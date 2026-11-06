"""PostgreSQL 16 for the tests: TEST_DATABASE_URL, else a temporary cluster (initdb and pg_ctl)."""

import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.db import sqlalchemy_url

PG_BIN = Path("/usr/lib/postgresql/16/bin")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def postgres_url():
    """The URL of a PostgreSQL server (the maintenance database 'postgres')."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield sqlalchemy_url(url)
        return
    if not (PG_BIN / "initdb").exists():
        pytest.skip("no PostgreSQL 16: set TEST_DATABASE_URL")
    tmp = Path(tempfile.mkdtemp(prefix="pgtest-"))
    data = tmp / "data"
    run_as = [] if os.geteuid() != 0 else ["runuser", "-u", "postgres", "--"]
    if run_as:
        shutil.chown(tmp, "postgres")
    subprocess.run([*run_as, str(PG_BIN / "initdb"), "-D", str(data), "-U", "postgres", "-A", "trust"],
                   check=True, capture_output=True)
    port = _free_port()
    subprocess.run([*run_as, str(PG_BIN / "pg_ctl"), "-D", str(data), "-l", str(tmp / "log"), "-w",
                    "-o", f"-p {port} -k {tmp} -c listen_addresses=127.0.0.1", "start"], check=True, capture_output=True)
    try:
        yield f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run([*run_as, str(PG_BIN / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def empty_database_url(postgres_url):
    """A new empty database for one test; it is dropped after the test."""
    name = "t_" + uuid.uuid4().hex[:12]
    admin = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    base = postgres_url.rsplit("/", 1)[0]
    try:
        yield f"{base}/{name}"
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def migrated_url(empty_database_url):
    """An empty database with all migrations."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return empty_database_url


@pytest.fixture
def sessions(migrated_url):
    """The sessionmaker of a migrated database; the app uses it for its requests in this test."""
    from app.db import get_session, make_engine, make_sessionmaker
    from app.main import app

    engine = make_engine(migrated_url)
    maker = make_sessionmaker(engine)

    def override():
        with maker() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield maker
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()
