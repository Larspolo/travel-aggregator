"""The penalty per transfer with no later captured connection, in "Advanced" (#1773)."""

import copy
import re

from sqlalchemy import event
from sqlalchemy.engine import Engine

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _three_legs():
    """Amsterdam → Basel → Zürich → Chur: two transfers."""
    o = copy.deepcopy(offer("89.90"))
    o["legs"][1]["to_name"] = "Zürich HB"
    o["legs"].append(dict(o["legs"][1], service_no="IC 3", from_name="Zürich HB", to_name="Chur",
                          depart_at="2026-12-20T15:37:00+01:00", arrive_at="2026-12-20T16:52:00+01:00"))
    return o


def _later_from_basel(final="Zürich HB"):
    o = copy.deepcopy(offer("40.00", "IC 63", "SBB"))
    o["legs"] = [dict(o["legs"][1], service_no="IC 63", to_name=final,
                      depart_at="2026-12-20T15:33:00+01:00", arrive_at="2026-12-20T16:26:00+01:00")]
    return o


def _score(page):
    """The effective cost of the only row."""
    return float(re.search(r'<div class="total">€([0-9.,]+)<', page).group(1).replace(",", ""))


def _count(client, url):
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        page = client.get(url).text
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    return page, len(statements)


def test_one_transfer_with_no_later_connection_adds_the_penalty(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    before = _score(client.get(f"/trips/{trip_id}?no_fallback_penalty=0").text)
    page = client.get(f"/trips/{trip_id}?no_fallback_penalty=30").text
    assert "€30 no later connection" in page
    assert _score(page) == before + 30


def test_two_transfers_with_no_later_connection_add_twice_the_penalty(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_three_legs()])
    assert "€60 no later connection" in client.get(f"/trips/{trip_id}?no_fallback_penalty=30").text


def test_a_later_connection_removes_the_part(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), _later_from_basel()])
    assert "no later connection" not in client.get(f"/trips/{trip_id}?no_fallback_penalty=30").text


def test_the_default_adds_no_part_and_no_query(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), _later_from_basel("Bern")])
    page, default = _count(client, f"/trips/{trip_id}")
    assert "no later connection" not in page and "€89.90" in page
    zero, zero_count = _count(client, f"/trips/{trip_id}?no_fallback_penalty=0")
    assert "no later connection" not in zero and zero_count == default
    on, on_count = _count(client, f"/trips/{trip_id}?no_fallback_penalty=30")
    assert "no later connection" in on and on_count > default


def test_advanced_has_the_field_and_the_url_checks_the_range(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    assert 'name="no_fallback_penalty"' in client.get(f"/trips/{trip_id}").text
    assert client.get(f"/trips/{trip_id}?no_fallback_penalty=1001").status_code == 422
