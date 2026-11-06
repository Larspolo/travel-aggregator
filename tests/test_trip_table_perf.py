"""The trip page stays fast with 1,000 offers: it answers in under 2 seconds and its count of SQL statements does
not grow with the count of offers (#115)."""

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def add_offers(client, auth, trip_id, start, count):
    for first in range(start, start + count, 100):  # the ingest takes the offers in batches
        ingest(client, auth, trip_id, [offer(f"{50 + n % 200}.90", f"ICE {n}")
                                       for n in range(first, min(first + 100, start + count))])


def statements_of_page(client, trip_id):
    count = []

    def on_execute(_conn, _cursor, statement, *_args):
        count.append(statement)

    event.listen(Engine, "before_cursor_execute", on_execute)
    try:
        started = time.perf_counter()
        r = client.get(f"/trips/{trip_id}")
        seconds = time.perf_counter() - started
    finally:
        event.remove(Engine, "before_cursor_execute", on_execute)
    assert r.status_code == 200
    return len(count), seconds, r.text


def test_the_page_with_1000_offers_is_fast_and_has_a_fixed_count_of_statements(trip):  # noqa: F811
    client, auth, trip_id = trip
    add_offers(client, auth, trip_id, 0, 10)
    few, _, _ = statements_of_page(client, trip_id)
    add_offers(client, auth, trip_id, 10, 990)
    client.get(f"/trips/{trip_id}")  # warm up the templates
    many, seconds, page = statements_of_page(client, trip_id)
    assert page.count("ICE ") >= 1000
    assert many == few, f"{few} statements with 10 offers, {many} with 1,000"
    assert seconds < 2, f"{seconds:.2f} s with 1,000 offers"
