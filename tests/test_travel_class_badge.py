"""The "1st" badge of a 1st class fare in the row fares and on the compare page (#692)."""

from sqlalchemy import select

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

BADGE = 'class="badge first-class"'


def _offer(price, service_no, fare, travel_class):
    o = offer(price, service_no, fare=fare)
    o["travel_class"] = travel_class
    return o


def _ids(sessions, trip_id):
    with sessions() as s:
        return list(s.scalars(select(Itinerary.id).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id)))


def test_a_first_class_fare_shows_the_badge_once(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_offer("150.00", "ICE 1", "Flexpreis", "first"),
                                   _offer("80.00", "ICE 2", "Sparpreis", "standard")])
    page = client.get(f"/trips/{trip_id}").text
    assert page.count(BADGE) == 1
    a, b = _ids(sessions, trip_id)
    compare = client.get(f"/trips/{trip_id}/compare?it={a}&it={b}").text
    assert compare.count(BADGE) == 1


def test_a_second_class_fare_shows_no_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_offer("80.00", "ICE 2", "Sparpreis", "standard")])
    assert BADGE not in client.get(f"/trips/{trip_id}").text


def test_a_fare_name_with_the_class_shows_no_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_offer("150.00", "ICE 1", "Flexpreis, 1st class", "first")])
    page = client.get(f"/trips/{trip_id}").text
    assert BADGE not in page and "1st class" in page
