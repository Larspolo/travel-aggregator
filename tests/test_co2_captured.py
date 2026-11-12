"""The captured CO₂ grams of the legs in the CO₂ of an offer (#2587)."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.co2 import co2_extras, co2_kg, co2_origin
from app.ranking import Weights, effective_cost
from tests.test_compare_tradeoff import timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
PRICED = Weights(co2_price_kg=Decimal("0.10"))


def _leg(mode, minutes, co2_g=None):
    dep = datetime(2026, 12, 20, 8, 0, tzinfo=UTC)
    return SimpleNamespace(mode=mode, depart_at=dep, arrive_at=dep + timedelta(minutes=minutes), co2_g=co2_g)


def test_captured_grams_replace_the_estimate():
    it = SimpleNamespace(legs=[_leg("train", 120, 10904)])
    assert co2_kg(it, PRICED) == Decimal("10.904")
    assert co2_origin(it) == "from the capture"
    assert co2_extras(it, PRICED) == (("CO₂ 11 kg (from the capture)", Decimal("1.09")),)


def test_no_grams_keep_the_estimate():
    it = SimpleNamespace(legs=[_leg("train", 120)])
    assert co2_kg(it, PRICED) == Decimal("6")
    assert co2_origin(it) == "estimate"


def test_mixed_legs_add_grams_and_estimate():
    it = SimpleNamespace(legs=[_leg("train", 60, 2000), _leg("bus", 90)])
    assert co2_kg(it, Weights()) == Decimal("2") + Decimal("1.5") * Decimal(Weights().co2_bus_kg_h)
    assert co2_origin(it) == "estimate"


def test_zero_price_keeps_the_score():
    it = SimpleNamespace(legs=[_leg("train", 120, 10904)])
    assert co2_extras(it, Weights()) == ()
    assert effective_cost(Decimal("100"), 0, 0, Weights(), ()).total == effective_cost(
        Decimal("100"), 0, 0, Weights(), co2_extras(it, Weights())).total


def test_row_shows_the_captured_value(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(timed("90.00", 5, "ICE 2"))
    o["legs"][0]["co2_g"] = 10904
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert "CO₂ about 11 kg per traveler (from the capture)" in page
