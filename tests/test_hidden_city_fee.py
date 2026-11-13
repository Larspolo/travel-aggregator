"""The hidden-city fee (#2794): "Hidden-city or throwaway ticket €" in "Advanced" adds the fee once to each fare that
has the mark of #2793, as the part "hidden-city ticket" or "throwaway ticket"; a fee of 0 or no mark changes nothing."""
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import hidden_city_extras
from tests.test_bike_fee import _totals
from tests.test_self_transfer import post
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)


def _marked(mark):
    o = offer("89.90")
    if mark is not None:
        o["travel_hack"] = mark
    return o


def test_the_fee_adds_one_part_for_each_mark():
    w = Weights(hidden_city_fee=Decimal("30"))
    assert hidden_city_extras(SimpleNamespace(travel_hack="hidden-city"), w) == (("hidden-city ticket", Decimal("30")),)
    assert hidden_city_extras(SimpleNamespace(travel_hack="throwaway"), w) == (("throwaway ticket", Decimal("30")),)


def test_no_mark_or_a_zero_fee_adds_no_part():
    assert hidden_city_extras(SimpleNamespace(travel_hack=None), Weights(hidden_city_fee=Decimal("30"))) == ()
    assert hidden_city_extras(SimpleNamespace(travel_hack="hidden-city"), Weights()) == ()


def test_the_page_adds_the_fee_to_a_marked_fare_only(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [_marked("hidden-city")])
    default = client.get(f"/trips/{trip_id}").text
    assert "€30 hidden-city ticket" not in default
    page = client.get(f"/trips/{trip_id}?hidden_city_fee=30").text
    assert "€30 hidden-city ticket" in page
    assert _totals(page)[0] == str(Decimal(_totals(default)[0]) + 30)


def test_an_unmarked_fare_does_not_change(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [_marked(None)])
    assert _totals(client.get(f"/trips/{trip_id}").text) == _totals(client.get(f"/trips/{trip_id}?hidden_city_fee=30").text)
