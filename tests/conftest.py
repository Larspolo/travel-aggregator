"""PostgreSQL 16 for the tests: TEST_DATABASE_URL, else a temporary cluster (initdb and pg_ctl)."""

import os
import shutil
import socket
import sys
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
import time_machine
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import Pool

from app.db import sqlalchemy_url
from tests import gh_annotations, shard

PG_BIN = Path("/usr/lib/postgresql/16/bin")

# The clock of all tests (#2543): the fixtures have fixed trip dates in the near future, and the app compares them with
# `datetime.now()`. With the real clock, each test with a date fails on the day that the real date passes it. The clock
# starts at this time in each test process (also in each xdist worker) and moves on (tick=True: timeouts and waits work).
# PostgreSQL follows it too: each database of the tests has `testclock.now()` (the real now() plus the offset of the
# test clock) before pg_catalog in the search_path, so a `server_default=func.now()` column has the time of the test.
# Not covered: the clock of the browser and of subprocesses. `tests/test_clock_fixed.py` checks it.
FIXED_START = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
_clock = time_machine.travel(FIXED_START, tick=True)
DB_CLOCK = """CREATE SCHEMA IF NOT EXISTS testclock;
CREATE OR REPLACE FUNCTION testclock.now() RETURNS timestamptz LANGUAGE sql STABLE AS
$$ SELECT pg_catalog.now() + coalesce(nullif(current_setting('testclock.shift', true), ''), '0')::interval $$"""


@event.listens_for(Pool, "connect")
def _db_clock(dbapi_connection, connection_record):
    """Each connection of the tests (the app, alembic, the tests) sees the database clock of the test clock."""
    if not type(dbapi_connection).__module__.startswith("psycopg"):
        return
    offset = time.time() - time_machine.escape_hatch.time.time()
    cursor = dbapi_connection.cursor()
    cursor.execute(f"SET search_path = testclock, \"$user\", public, pg_catalog; SET testclock.shift = '{offset:.6f} s'")
    cursor.close()
    dbapi_connection.commit()


def pytest_configure(config):
    _clock.start()


def pytest_unconfigure(config):
    _clock.stop()


def pytest_addoption(parser):
    parser.addoption("--shard", default=None, metavar="K/N",
                     help="run only part K of N of the selected tests: whole files (tests/shard.py, #1062)")


PARALLEL_FILES = 3   # from 3 files, xdist is faster: 3 files 8.6 s -> 6.7 s, 6 files 15.0 s -> 9.3 s (4 CPUs, #1890)


def parallel_workers(option, args):
    """The xdist workers for a call that names test files and no -n: one for each file, at most 'auto'. None: no change.
    A worker starts its own cluster (about 2 s), so 1 or 2 files run faster with no xdist. The quick CI runs all fast
    tests with -n auto, so each fast test can run in a worker."""
    if getattr(option, "numprocesses", 0) is not None or getattr(option, "dist", "no") != "no":
        return None                                    # no xdist, or -n / --dist given (-n 0 keeps one process)
    if option.collectonly or option.usepdb or "slow" in (option.markexpr or "").replace("not slow", ""):
        return None
    files = {a.split("::")[0] for a in args if a.split("::")[0].endswith(".py")}
    return len(files) if len(files) >= PARALLEL_FILES else None


@pytest.hookimpl(tryfirst=True)   # before the hook of xdist that reads -n
def pytest_cmdline_main(config):
    n = parallel_workers(config.option, config.args)
    if n and not os.environ.get("PYTEST_XDIST_WORKER"):
        config.option.numprocesses = "auto"
        config.option.maxprocesses = min(n, config.option.maxprocesses or n)


@pytest.hookimpl(trylast=True)   # after `-m slow` deselects the other tests: the parts split only the selected tests
def pytest_collection_modifyitems(config, items):
    value = config.getoption("--shard")
    if not value:
        return
    try:
        k, n = shard.parse(value)
    except ValueError as e:
        raise pytest.UsageError(str(e)) from None
    kept, dropped = shard.select(items, k, n)
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept


def pytest_terminal_summary(terminalreporter):
    """In GitHub Actions, the failed tests as annotations: ship_pr.py prints them for a red CI (#1443)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    stats = terminalreporter.stats
    for line in gh_annotations.lines(stats.get("failed", []) + stats.get("error", [])):
        terminalreporter.write_line(line)


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


@contextmanager
def _database(postgres_url, template=None):
    """The URL of a new database (a copy of `template`, else empty); it is dropped at the end."""
    name = "t_" + uuid.uuid4().hex[:12]
    copy = f' TEMPLATE "{template}"' if template else ""   # the default STRATEGY WAL_LOG: FILE_COPY was slower
    admin = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"{copy}'))
    base = postgres_url.rsplit("/", 1)[0]
    if not template:   # a copy of the template has the function of the clock
        clock = create_engine(f"{base}/{name}")
        with clock.begin() as c:
            c.exec_driver_sql(DB_CLOCK)
        clock.dispose()
    try:
        yield f"{base}/{name}"
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _upgrade(url):
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def empty_database_url(postgres_url):
    """A new empty database for one test; it is dropped after the test."""
    with _database(postgres_url) as url:
        yield url


@pytest.fixture(scope="session")
def migrated_template(postgres_url):
    """The name of a database with all migrations, made once in each test process (each xdist worker). The
    migrations of each test took about 0.2 s, for about 650 tests of the quick CI (#1070)."""
    with _database(postgres_url) as url:
        _upgrade(url)
        yield url.rsplit("/", 1)[1]


@pytest.fixture
def migrated_url(postgres_url, migrated_template):
    """A database with all migrations for one test: a copy of `migrated_template`; it is dropped after the test."""
    with _database(postgres_url, template=migrated_template) as url:
        yield url


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


def app_state():
    """The module-level objects of `app` with a `reset()` method (the limiters of #145 and #412, a later cache): global
    state of all tests. `tests/test_app_global_state.py` fails for global state with no `reset()`."""
    import app.main  # noqa: F401 (loads all modules of the app)

    found = {}
    for name, module in list(sys.modules.items()):
        if name == "app" or name.startswith("app."):
            for obj in vars(module).values():
                if (not isinstance(obj, type) and type(obj).__module__.startswith("app.")
                        and callable(getattr(obj, "reset", None))):
                    found[id(obj)] = obj
    return list(found.values())


@pytest.fixture
def app_state_objects():
    """The objects that `_reset_limiters` resets (app_state)."""
    return app_state()


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Each test starts with empty limiters and caches: all TestClient requests come from one address, so 20 bad
    tokens of earlier tests locked the API for a later test (#521). The fixture finds each one (app_state)."""
    state = app_state()
    for obj in state:
        obj.reset()
    yield
    for obj in state:
        obj.reset()


@pytest.fixture(autouse=True)
def _departed_clock(monkeypatch):
    """The fixtures have fixed dates: with the real time they depart and the trip page hides them (#1391).
    A test of the departed offers sets its own clock."""
    from datetime import datetime, timezone

    import app.departed
    monkeypatch.setattr(app.departed, "clock", lambda: datetime(2000, 1, 1, tzinfo=timezone.utc))
