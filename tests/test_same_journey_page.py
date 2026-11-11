""""Same journey" in the bulk bar and "Not the same journey" in the expanded row of the trip page (#2145)."""

from sqlalchemy import select

from app.models import Fare, Itinerary
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _rows(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id)).all()
        return [(it.id, it.merged_into_id, len(it.fares)) for it in its]


def _bulk(client, trip_id, ids):
    return client.post(f"/trips/{trip_id}/itineraries/bulk?action=join",
                       data={"csrf_token": csrf(client, trip_id), "it": ids})


def _three(client, auth, trip_id, fares=("Sparpreis", "Flexpreis", "Super")):
    ingest(client, auth, trip_id, [offer("89.90", "ICE 1", fare=fares[0]), offer("99.90", "ICE 2", fare=fares[1]),
                                   offer("109.90", "ICE 3", fare=fares[2])])


def test_same_journey_joins_two_rows_and_not_the_same_journey_splits_them(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _three(client, auth, trip_id)
    (a, _, _), (b, _, _), _ = _rows(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert "Same journey" in page and "Not the same journey" not in page
    page = _bulk(client, trip_id, [a, b]).text
    assert "The 2 rows are joined into one row." in page and "Joined from 2 rows" in page
    assert _rows(sessions, trip_id)[:2] == [(a, None, 2), (b, a, 0)]
    page = client.post(f"/trips/{trip_id}/itineraries/{a}/split/{b}",
                       data={"csrf_token": csrf(client, trip_id)}).text
    assert "The row is split into 2 rows." in page and "Joined from" not in page
    assert _rows(sessions, trip_id)[:2] == [(a, None, 1), (b, None, 1)]


def test_one_or_three_rows_give_a_message_and_no_change(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _three(client, auth, trip_id)
    before = _rows(sessions, trip_id)
    for ids in ([before[0][0]], [r[0] for r in before]):
        assert "Select exactly 2 rows" in _bulk(client, trip_id, ids).text
    assert _rows(sessions, trip_id) == before


def test_two_rows_with_the_same_source_and_fare_name_give_the_message_of_join(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _three(client, auth, trip_id, fares=("Sparpreis", "Sparpreis", "Super"))
    before = _rows(sessions, trip_id)
    with sessions() as s:
        assert len(s.scalars(select(Fare)).all()) == 3
    page = _bulk(client, trip_id, [before[0][0], before[1][0]]).text
    assert "Not joined: both rows have the fare" in page and "they cannot be joined" in page
    assert _rows(sessions, trip_id) == before
