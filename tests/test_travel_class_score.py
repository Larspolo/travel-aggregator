"""The 1st class amount per hour in the effective cost (#691)."""

from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.travelclass import class_extras
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def test_a_first_class_fare_of_two_hours_gets_the_bonus():
    w = Weights(first_class_hour=Decimal("-10"))
    assert class_extras(SimpleNamespace(travel_class="first"), 120, w) == (("1st class", Decimal("-20")),)


def test_a_standard_fare_and_an_amount_of_zero_add_no_part():
    w = Weights(first_class_hour=Decimal("-10"))
    assert class_extras(SimpleNamespace(travel_class="standard"), 120, w) == ()
    assert class_extras(SimpleNamespace(travel_class=None), 120, w) == ()
    assert class_extras(SimpleNamespace(travel_class="first"), 120, Weights()) == ()


def test_the_bonus_shows_in_the_breakdown_and_the_panel(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = direct("100.00")
    o.update(travel_class="first")
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}?first_class_hour=-10").text
    assert "€100 price + €60 time + €-40 1st class = €120" in page
    assert 'name="first_class_hour"' in page
