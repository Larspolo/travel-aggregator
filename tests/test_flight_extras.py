"""The airport buffer and the baggage fee of a flight (#99)."""

from decimal import Decimal
from types import SimpleNamespace

from app.door import flight_extras
from app.ranking import Weights
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _it(*modes):
    return SimpleNamespace(legs=[SimpleNamespace(mode=m) for m in modes])


def test_flight_with_defaults():
    assert flight_extras(_it("train", "flight"), Weights()) == (("airport time", Decimal("37.5")),
                                                                 ("baggage", Decimal("0")))


def test_train_has_no_airport_part():
    assert flight_extras(_it("train", "bus"), Weights()) == ()


def test_zero_disables_and_baggage_fee_counts():
    w = Weights(airport_before_min=0, airport_after_min=0, baggage_fee=Decimal("35"))
    assert flight_extras(_it("flight"), w) == (("airport time", Decimal("0")), ("baggage", Decimal("35")))


def _flight(price):
    o = direct(price)
    o["legs"][0].update(mode="flight", service_no="KL 1")
    return o


def test_advanced_inputs_change_the_order(trip):  # noqa: F811
    client, auth, trip_id = trip
    # Both 4 h, no transfer: 60 time. Flight 100 + 60 + 37.50 airport = 197.50; train 180 + 60 = 240.
    ingest(client, auth, trip_id, [_flight("100.00"), direct("180.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert "<details" in page and "<details open" not in page and 'name="baggage_fee"' in page
    assert "€100 price + €60 time + €37.50 airport time = €197.50" in page
    assert page.index("= €197.50") < page.index("= €240")
    page = client.get(f"/trips/{trip_id}?baggage_fee=50&airport_before_min=180").text
    # 100 + 60 + (180 + 30) × 15 / 60 = 52.50 + 50 = 262.50
    assert "€52.50 airport time + €50 baggage = €262.50" in page
    assert page.index("= €240") < page.index("= €262.50")
    assert client.get(f"/trips/{trip_id}?baggage_fee=-1").status_code == 422
