"""The trip page hides the offers that arrive after the "arrive by" time of the trip (#1296)."""

from datetime import time

from app.models import Trip
from tests.test_trip_filter_times import timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _set_arrive_by(sessions, trip_id, value):
    with sessions() as s:
        s.get(Trip, trip_id).arrive_by = time.fromisoformat(value) if value else None
        s.commit()


def _two_offers(client, auth, trip_id):
    ingest(client, auth, trip_id, [timed("OK 1", "2026-12-20T09:00:00+01:00", "2026-12-20T13:50:00+01:00"),
                                   timed("LATE 2", "2026-12-20T09:30:00+01:00", "2026-12-20T14:20:00+01:00")])


def test_arrive_by_hides_the_offer_that_arrives_after_it(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_arrive_by(sessions, trip_id, "14:00")
    _two_offers(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert "OK 1" in page and "LATE 2" not in page
    assert 'value="14:00"' in page  # the arrival box shows the limit


def test_a_latest_arrive_in_the_query_wins_over_arrive_by(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_arrive_by(sessions, trip_id, "14:00")
    _two_offers(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}?latest_arrive=15:00").text
    assert "OK 1" in page and "LATE 2" in page


def test_a_trip_without_arrive_by_shows_both(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_arrive_by(sessions, trip_id, None)
    _two_offers(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert "OK 1" in page and "LATE 2" in page
