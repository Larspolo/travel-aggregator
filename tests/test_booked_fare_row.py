"""A booked row of the trip page shows the paid price and the price now (#1147, epic #1145)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models import Itinerary
from tests.test_trip_booked import _itinerary_id
from tests.test_trip_booked import trip as booked_trip  # noqa: F401


def _book(sessions, trip_id, price, fare_now=None):
    it_id = _itinerary_id(sessions, trip_id)
    with sessions() as s:
        it = s.get(Itinerary, it_id)
        fare = it.fares[0]
        if fare_now is not None:
            fare.latest_price = Decimal(fare_now)
        it.booked = True
        if price is not None:
            it.booked_fare_id, it.booked_price, it.booked_currency = fare.id, Decimal(price), "EUR"
            it.booked_at = datetime(2026, 11, 1, tzinfo=UTC)
        s.commit()


def _route_cell(client, trip_id):
    html = client.get(f"/trips/{trip_id}").text
    return html.split('class="route-name"')[1].split('class="facts"')[0]


def test_a_higher_price_now_shows_the_rise(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    _book(sessions, trip_id, "59.80", fare_now="89.00")
    cell = _route_cell(client, trip_id)
    assert "Paid €59.80" in cell
    assert "now €89.00 (+€29.20)" in cell


def test_a_lower_price_now_shows_the_drop(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    _book(sessions, trip_id, "59.80", fare_now="49.00")
    assert "now €49.00 (−€10.80)" in _route_cell(client, trip_id)


def test_the_same_price_shows_only_the_paid_price(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    _book(sessions, trip_id, "59.80", fare_now="59.80")
    cell = _route_cell(client, trip_id)
    assert "Paid €59.80" in cell
    assert "now" not in cell


def test_an_old_booked_row_shows_only_booked(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    _book(sessions, trip_id, None)
    cell = _route_cell(client, trip_id)
    assert "booked" in cell
    assert "Paid" not in cell
