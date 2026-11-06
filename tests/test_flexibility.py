"""Flexibility tiers in the effective cost (#175)."""

from types import SimpleNamespace
from decimal import Decimal

from app.flexibility import flexibility_extras, tier
from app.ranking import Weights
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _fare(price, name, flexibility):
    o = direct(price)
    o.update(fare_name=name, flexibility=flexibility)
    return o


def test_texts_map_to_tiers():
    assert tier("non_refundable") == tier("Non-refundable") == tier("nonrefundable") == "non_refundable"
    assert tier("flexible") == tier("refundable") == "flexible"
    assert tier("partly refundable") == "partly_refundable"
    assert tier(None) is None and tier("") is None and tier("gold") is None


def test_unknown_text_and_zero_amounts_add_no_part():
    w = Weights(flex_non_refundable=Decimal("15"))
    assert flexibility_extras(SimpleNamespace(flexibility="gold"), w) == ()
    assert flexibility_extras(SimpleNamespace(flexibility="non_refundable"), Weights()) == ()
    assert flexibility_extras(SimpleNamespace(flexibility="non_refundable"), w) == (("non-refundable", Decimal("15")),)


def test_non_refundable_penalty_shows_in_the_breakdown(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_fare("100.00", "Sparpreis", "non_refundable")])
    page = client.get(f"/trips/{trip_id}?flex_non_refundable=15").text
    assert "€100 price + €60 time + €15 non-refundable = €175" in page
    assert 'name="flex_flexible"' in page


def test_flexible_bonus_makes_the_flexible_fare_the_main_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_fare("100.00", "Sparpreis", "non_refundable"),
                                   _fare("105.00", "Flexpreis", "flexible")])
    page = client.get(f"/trips/{trip_id}?flex_flexible=-10").text
    assert "€105 price + €60 time + €-10 flexible = €155" in page
    assert "<td>Flexpreis<div" in page and "<td>Sparpreis<div" not in page


def test_zero_amounts_and_unknown_text_keep_the_cheapest_fare(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_fare("100.00", "Sparpreis", "gold"), _fare("105.00", "Flexpreis", "flexible")])
    page = client.get(f"/trips/{trip_id}?flex_non_refundable=15").text
    assert "€100 price + €60 time = €160" in page
    assert "<td>Sparpreis<div" in page and "<td>Flexpreis<div" not in page
