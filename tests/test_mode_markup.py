"""The mode markup or discount: a flat amount for each mode an itinerary uses, once per itinerary (#174)."""

from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost
from app.risk import mode_extras
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _it(mode_summary):
    return SimpleNamespace(mode_summary=mode_summary)


def test_a_bus_markup_is_one_part_per_itinerary_with_that_mode():
    w = Weights(bus_markup=Decimal("20"))
    assert mode_extras(_it("bus"), w) == (("bus markup", Decimal("20")),)
    assert mode_extras(_it("train+bus"), w) == (("bus markup", Decimal("20")),)
    assert mode_extras(_it("train"), w) == ()


def test_a_negative_flight_markup_lowers_the_cost_by_that_amount():
    w = Weights(flight_markup=Decimal("-10"))
    extras = mode_extras(_it("flight"), w)
    assert extras == (("flight markup", Decimal("-10")),)
    assert effective_cost(Decimal("100"), 0, 0, w, extras).total == Decimal("90.00")


def test_a_markup_of_zero_adds_no_part():
    assert mode_extras(_it("train+bus+flight+ferry"), Weights()) == ()


def test_the_page_shows_the_bus_markup_once_for_a_train_and_bus_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = direct("100.00")
    second = dict(o["legs"][0], mode="bus", carrier="Flixbus", service_no="FLX 2", from_name=o["legs"][0]["to_name"],
                  to_name="München", depart_at="2026-12-20T14:00:00+01:00", arrive_at="2026-12-20T15:00:00+01:00")
    o["legs"] = [o["legs"][0], second]
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}?bus_markup=20").text
    assert page.count("bus markup") == 1
    assert "bus markup" not in client.get(f"/trips/{trip_id}").text
