"""The trips list shows the count of new offers of each trip since its last full view (#1091)."""

from sqlalchemy import event

from app.web.pages import new_by_trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trips_list_drops import _other_trip


def test_a_viewed_trip_shows_the_new_offers_until_the_next_view(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    client.get(f"/trips/{trip_id}")
    ingest(client, auth, trip_id, [offer("50.00", "ICE 1"), offer("60.00", "ICE 2"), offer("70.00", "ICE 3")])
    assert "3 new" in client.get("/").text
    client.get(f"/trips/{trip_id}")
    assert " new</span>" not in client.get("/").text


def test_a_trip_never_viewed_shows_no_count(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    assert " new</span>" not in client.get("/").text
    with sessions() as s:
        assert new_by_trip(s) == {}


def test_the_counts_take_one_query(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    other = _other_trip(sessions)
    for t in (trip_id, other):
        ingest(client, auth, t, [offer("99.90", "ICE 105")])
        client.get(f"/trips/{t}")
        ingest(client, auth, t, [offer("50.00", "ICE 1")])
    with sessions() as s:
        statements = []
        listener = lambda *a: statements.append(a[2])  # noqa: E731
        event.listen(s.get_bind(), "before_cursor_execute", listener)
        try:
            assert new_by_trip(s) == {trip_id: 1, other: 1}
        finally:
            event.remove(s.get_bind(), "before_cursor_execute", listener)
        assert len(statements) == 1
