"""The owner corrects the paid fare and price of a booked row (#1148, epic #1145)."""

import copy
import re
from decimal import Decimal

from app import tokens
from app.models import Fare, Itinerary
from tests.test_trip_booked import _itinerary_id, booked_url, csrf
from tests.test_trip_booked import trip as booked_trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_page import BODY, offer


def _paid_url(trip_id, itinerary):
    return f"/trips/{trip_id}/itineraries/{itinerary}/paid"


def _ingest(client, sessions, trip_id, source, price, service_no="ICE 105"):
    with sessions() as s:
        token = tokens.create(s, "paid test")
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=[offer(price, service_no)])
    assert client.post("/api/ingest", json=body, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def _fare_id(sessions, itinerary, source):
    with sessions() as s:
        return s.query(Fare).filter_by(itinerary_id=itinerary, source=source).one().id


def _paid(sessions, itinerary):
    with sessions() as s:
        it = s.get(Itinerary, itinerary)
        return it.booked_fare_id, it.booked_price, it.booked_currency


def _post(client, trip_id, itinerary, fare_id, price):
    data = {"csrf_token": csrf(client, trip_id), "fare_id": str(fare_id), "price": price}
    return client.post(_paid_url(trip_id, itinerary), data=data, follow_redirects=False)


def _booked_with_two_fares(client, sessions, trip_id):
    """One booked itinerary with a bahn.de fare of 89.90 and a Trainline fare of 64.30 (the same connection)."""
    it = _itinerary_id(sessions, trip_id)
    assert client.post(booked_url(trip_id, it), data={"csrf_token": csrf(client, trip_id)},
                       follow_redirects=False).status_code == 303
    _ingest(client, sessions, trip_id, "thetrainline.com", "64.30")
    return it


def test_a_second_fare_and_price_are_stored_and_the_row_shows_the_paid_price(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    it = _booked_with_two_fares(client, sessions, trip_id)
    fare = _fare_id(sessions, it, "thetrainline.com")
    r = _post(client, trip_id, it, fare, "64.30")
    assert r.status_code == 303
    assert _paid(sessions, it) == (fare, Decimal("64.30"), "EUR")
    assert "Paid €64.30" in client.get(f"/trips/{trip_id}").text


def test_a_blank_negative_or_bad_price_is_422_and_stores_nothing(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    it = _booked_with_two_fares(client, sessions, trip_id)
    fare = _fare_id(sessions, it, "thetrainline.com")
    before = _paid(sessions, it)
    for price in ["", "   ", "-1", "abc", "NaN", "64.305", "100000", "1e5"]:
        assert _post(client, trip_id, it, fare, price).status_code == 422, price
    assert _paid(sessions, it) == before


def test_a_fare_of_another_itinerary_is_422(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    it = _booked_with_two_fares(client, sessions, trip_id)
    _ingest(client, sessions, trip_id, "bahn.de", "70.00", service_no="ICE 999")
    other_fare = _fare_id(sessions, _other_itineraries(sessions, trip_id, it)[0], "bahn.de")
    assert _post(client, trip_id, it, other_fare, "70.00").status_code == 422
    assert _paid(sessions, it)[0] != other_fare


def test_a_row_that_is_not_booked_is_409(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    it = _itinerary_id(sessions, trip_id)
    _ingest(client, sessions, trip_id, "thetrainline.com", "64.30")
    fare = _fare_id(sessions, it, "thetrainline.com")
    assert _post(client, trip_id, it, fare, "64.30").status_code == 409


def test_the_form_has_a_label_for_each_control(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    it = _booked_with_two_fares(client, sessions, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    for control in (f"paid-fare-{it}", f"paid-price-{it}"):
        assert f'for="{control}"' in page and f'id="{control}"' in page
    assert re.search(rf'action="/trips/{trip_id}/itineraries/{it}/paid"', page)


def _other_itineraries(sessions, trip_id, it):
    with sessions() as s:
        return [i.id for i in s.query(Itinerary).filter_by(trip_id=trip_id) if i.id != it]
