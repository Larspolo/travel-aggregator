"""The fee per leg of a fare with a bicycle reservation on a trip with a bicycle (#2475): "Bicycle € per leg" in
"Advanced" adds the fee for each leg of a "reservation" fare as the part "bicycle" of the breakdown."""
from decimal import Decimal
from types import SimpleNamespace

from app.models import Trip
from app.ranking import Weights
from app.risk import bike_extras
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _itinerary(legs, bike=True):
    return SimpleNamespace(legs=[None] * legs, trip=SimpleNamespace(bike=bike))


def test_the_fee_per_leg_adds_the_part_for_a_reservation():
    w = Weights(bike_fee=Decimal("9"))
    fare = SimpleNamespace(bike="reservation")
    assert bike_extras(fare, _itinerary(1), w) == (("bicycle", Decimal("9")),)
    assert bike_extras(fare, _itinerary(2), w) == (("bicycle", Decimal("18")),)


def test_a_zero_fee_an_allowed_no_or_missing_bike_or_a_trip_without_bike_adds_no_part():
    w = Weights(bike_fee=Decimal("9"))
    assert bike_extras(SimpleNamespace(bike="reservation"), _itinerary(1), Weights()) == ()
    assert bike_extras(SimpleNamespace(bike="allowed"), _itinerary(1), w) == ()
    assert bike_extras(SimpleNamespace(bike="no"), _itinerary(1), w) == ()
    assert bike_extras(SimpleNamespace(bike=None), _itinerary(1), w) == ()
    assert bike_extras(SimpleNamespace(bike="reservation"), _itinerary(1, bike=False), w) == ()
    assert bike_extras(SimpleNamespace(bike="reservation"), SimpleNamespace(legs=[None], trip=None), w) == ()


def _bike_offer(*status):
    o = reserved(*status)
    o["bike"] = "reservation"
    return o


def _totals(page):
    return [line.rsplit("= €", 1)[1].split("<")[0].strip() for line in page.split("\n") if "= €" in line]


def _set_bike(sessions, trip_id, value):
    with sessions() as s:
        s.get(Trip, trip_id).bike = value
        s.commit()


def test_the_breakdown_and_the_score_of_a_bicycle_trip_with_a_reservation(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_bike(sessions, trip_id, True)
    post(client, auth, trip_id, [_bike_offer("required", None, None)])
    default = client.get(f"/trips/{trip_id}").text
    assert "bicycle =" not in default
    page = client.get(f"/trips/{trip_id}?bike_fee=9").text
    assert "bicycle =" in page
    assert f"€27 bicycle = €{Decimal(_totals(default)[0]) + 27}" in page  # 3 legs x €9: the score is €27 higher


def test_a_trip_without_bicycle_does_not_change(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_bike(sessions, trip_id, False)
    post(client, auth, trip_id, [_bike_offer("required", None, None)])
    assert _totals(client.get(f"/trips/{trip_id}").text) == _totals(client.get(f"/trips/{trip_id}?bike_fee=9").text)
