"""A platform change of a booked leg shows on the Upcoming, trip and print pages (#2684)."""

from sqlalchemy import select

from app.models import Itinerary, Leg, Trip
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)
from tests.test_leg_platforms_page import book_with_platforms, client  # noqa: F401  (client is a fixture)


def set_booked(sessions, booked_from, booked_to):
    with sessions() as s:
        leg = s.scalars(select(Leg)).one()
        leg.booked_from_platform, leg.booked_to_platform = booked_from, booked_to
        s.commit()
        trip_id = s.scalars(select(Trip.id)).one()
        it_id = s.scalars(select(Itinerary.id)).one()
    return trip_id, it_id


def pages(client, trip_id, it_id):  # noqa: F811
    return [client.get("/upcoming").text, client.get(f"/upcoming?only={it_id}").text]


def test_a_changed_platform_shows_on_all_pages(client, sessions):  # noqa: F811
    book_with_platforms(sessions, "11", "5")
    trip_id, it_id = set_booked(sessions, "8b", "4")
    for page in pages(client, trip_id, it_id):
        assert "Platform changed: 8b now 11" in page
        assert "Arrival platform changed: 4 now 5" in page


def test_the_same_platform_shows_no_change(client, sessions):  # noqa: F811
    book_with_platforms(sessions, "11", "5")
    trip_id, it_id = set_booked(sessions, "11", "5")
    for page in pages(client, trip_id, it_id):
        assert "platform-change" not in page


def test_the_platforms_are_escaped(client, sessions):  # noqa: F811
    book_with_platforms(sessions, "<b>1", "5")
    trip_id, it_id = set_booked(sessions, "8b", None)
    for page in pages(client, trip_id, it_id):
        assert "Platform changed: 8b now &lt;b&gt;1" in page


def trip_page(trip, sessions, booked_from, booked_to):  # noqa: F811
    web, auth, trip_id = trip
    offer = reserved(None, None)
    offer["legs"][0]["from_platform"] = "11"
    offer["legs"][0]["to_platform"] = "5"
    assert post(web, auth, trip_id, [offer])["created"] == 1
    with sessions() as s:
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).one()
        it.booked = True
        it.legs[0].booked_from_platform, it.legs[0].booked_to_platform = booked_from, booked_to
        s.commit()
    return web.get(f"/trips/{trip_id}").text


def test_a_changed_platform_shows_on_the_trip_page(trip, sessions):  # noqa: F811
    page = trip_page(trip, sessions, "8b", "4")
    assert "Platform changed: 8b now 11" in page
    assert "Arrival platform changed: 4 now 5" in page


def test_the_same_platform_shows_no_change_on_the_trip_page(trip, sessions):  # noqa: F811
    assert "platform-change" not in trip_page(trip, sessions, "11", "5")
