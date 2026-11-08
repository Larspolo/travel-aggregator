"""The trip page stays fast with 1,000 offers: it answers in under 2 seconds and its count of SQL statements does
not grow with the count of offers (#115).

The test compares the fastest of 3 loads with the limit: in the quick CI, the other test workers use the same CPUs,
and one load took 2.05 s on a main commit that changed only the README (#1063)."""

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
    loads = [statements_of_page(client, trip_id) for _ in range(3)]
    for many, _, page in loads:
        assert page.count("ICE ") >= 1000
        assert many == few, f"{few} statements with 10 offers, {many} with 1,000"
    seconds = sorted(load[1] for load in loads)
    assert seconds[0] < 2, f"{', '.join(f'{s:.2f}' for s in seconds)} s with 1,000 offers"
