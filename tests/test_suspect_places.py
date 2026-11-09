"""The days and the booked-drop message use no suspect fare (#1639, epic #1603).
The panel and "Best by profile": `tests/test_suspect_trip_page.py`. A test double replaces the POST."""

from decimal import Decimal

from tests.test_booked_drop import _book, flex
from tests.test_notify_ntfy import _channel, sent  # noqa: F401  (sent is a fixture)
from tests.test_suspect_trip_page import later
from tests.test_trip_days import captured  # noqa: F401  (captured is a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def test_the_best_and_cheapest_of_a_day_are_no_suspect_fare(trip, captured):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("39.00", "ICE 1"), offer("45.00", "ICE 2")])
    later(client, auth, tid, [offer("3.50", "ICE 1"), offer("45.00", "ICE 2")])
    assert client.get(f"/trips/{tid}").status_code == 200
    days = [d for d in captured[-1]["days"] if d.best is not None]
    assert days
    for day in days:
        assert day.best[1].latest_price == Decimal("45.00")
        assert day.cheapest[1].latest_price == Decimal("45.00")


def test_a_suspect_price_of_a_booked_fare_makes_no_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions)
    ingest(client, auth, trip_id, [flex("89.00")])
    _book(sessions, trip_id)
    ingest(client, auth, trip_id, [flex("9.00")])  # below a fifth of €89: suspect
    assert sent == []
