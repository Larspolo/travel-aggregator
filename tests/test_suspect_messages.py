"""A suspect fare is not the best price of the trips list, is not at target and makes no price-drop message (#1606).
A test double replaces the POST: no request leaves the test."""

from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary
from app.target import at_target
from app.trips import list_trips
from tests.test_suspect_fares import _fare, _trip
from tests.test_target_notify import _setup, sent  # noqa: F401  (sent is a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def test_the_trips_list_shows_the_usable_best_price(sessions):
    with sessions() as s:
        t = _trip(s)
        _fare(s, t, [(1, "39.00", "EUR"), (2, "3.50", "EUR")], n=1)
        _fare(s, t, [(1, "45.00", "EUR")], n=2)
        s.commit()
        row = next(r for r in list_trips(s) if r.id == t.id)
        assert row.best_price == Decimal("45.00")


def test_a_suspect_fare_is_not_at_target(sessions):
    with sessions() as s:
        t = _trip(s)
        _fare(s, t, [(1, "39.00", "EUR"), (2, "3.50", "EUR")], n=1)
        t.target_price = Decimal("20")
        s.commit()
        assert at_target(s, t) == []


def _pin(sessions, trip_id):
    with sessions() as s:
        for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)):
            it.pinned = True
        s.commit()


def test_a_suspect_drop_makes_no_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id, target="20.00")
    ingest(client, auth, trip_id, [offer("39.00")])
    _pin(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("3.50")])
    assert sent == []  # neither the pinned drop nor the target of €20 (the list check: the test above)


def test_a_plausible_drop_still_makes_the_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id, target=None)
    ingest(client, auth, trip_id, [offer("39.00")])
    _pin(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("30.00")])
    assert len(sent) == 1 and "EUR 30.00" in sent[0][1]
