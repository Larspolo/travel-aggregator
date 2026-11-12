"""The tests run with a fixed clock (#2543): a date in a test does not fail on the day that the real date passes it."""

import threading
import time
from datetime import date, datetime, timedelta, timezone

from tests.conftest import FIXED_START


def test_the_clock_of_a_test_is_the_fixed_day():
    assert FIXED_START == datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    # tick=True: the clock moves on from the fixed start, but a test process runs for less than 3 hours
    assert FIXED_START <= now < FIXED_START + timedelta(hours=3)
    assert date.today() == FIXED_START.date()
    assert FIXED_START.timestamp() <= time.time() < FIXED_START.timestamp() + 3 * 3600


def test_the_clock_moves_on():
    first = datetime.now(timezone.utc)
    time.sleep(0.01)
    assert datetime.now(timezone.utc) > first


def test_a_thread_has_the_same_clock():
    """The live server of a browser test runs in a thread of the test process."""
    seen = []
    thread = threading.Thread(target=lambda: seen.append(datetime.now(timezone.utc)))
    thread.start()
    thread.join()
    assert FIXED_START <= seen[0] < FIXED_START + timedelta(hours=3)


def test_the_database_clock_is_the_fixed_day(sessions):
    """A `server_default=func.now()` column (for example `captures.received_at`, #1868) has the time of the test."""
    from sqlalchemy import text

    with sessions() as s:
        db_now = s.scalar(text("SELECT now()"))
    assert FIXED_START <= db_now < FIXED_START + timedelta(hours=3)
    assert abs(db_now - datetime.now(timezone.utc)) < timedelta(minutes=1)


def test_a_new_empty_database_has_the_clock(empty_database_url):
    """A migration test makes its tables in an empty database: their defaults use the clock of the test too."""
    from sqlalchemy import create_engine, text

    engine = create_engine(empty_database_url)
    with engine.connect() as c:
        db_now = c.scalar(text("SELECT now()"))
    engine.dispose()
    assert FIXED_START <= db_now < FIXED_START + timedelta(hours=3)
