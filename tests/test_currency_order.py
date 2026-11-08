"""The fares and the price drops are ordered by their EUR value, not by their number (#425)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.currency import by_eur
from app.drops import drops_by_trip
from app.models import CurrencyRate, Fare, Itinerary, Leg, Trip
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

T = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
RATES = {"CZK": Decimal("0.04"), "USD": Decimal("0.9")}


def _fare(price, currency):
    return SimpleNamespace(latest_price=Decimal(price), currency=currency)


def test_by_eur_puts_the_cheaper_eur_value_first():
    czk, eur = _fare("500", "CZK"), _fare("25", "EUR")  # CZK 500 is EUR 20.00
    assert by_eur([eur, czk], RATES) == [czk, eur]


def test_by_eur_puts_a_fare_with_no_rate_last():
    no_rate, czk, eur = _fare("1", "XXX"), _fare("500", "CZK"), _fare("25", "EUR")
    assert by_eur([no_rate, eur, czk], RATES) == [czk, eur, no_rate]


def test_trip_page_lists_the_czk_fare_first(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    with sessions() as s:
        s.add(CurrencyRate(code="CZK", eur_per_unit=Decimal("0.04"), updated_at=T))
        it = Itinerary(trip_id=trip_id, fingerprint="order-1", depart_at=T, arrive_at=T, duration_min=60)
        it.legs.append(Leg(seq=0, mode="train", from_name="A", to_name="B", depart_at=T, depart_offset_min=60,
                           arrive_at=T, arrive_offset_min=60))
        it.fares.append(Fare(source="a", latest_price=Decimal("25"), currency="EUR", latest_captured_at=T))
        it.fares.append(Fare(source="b", latest_price=Decimal("500"), currency="CZK", latest_captured_at=T))
        it.fares.append(Fare(source="c", latest_price=Decimal("1"), currency="XXX", latest_captured_at=T))
        s.add(it)
        s.commit()
    html = client.get(f"/trips/{trip_id}").text
    fares = html[html.index('<div class="fares">'):]
    fares = fares[:fares.index("<form")]
    assert fares.index("CZK 500.00") < fares.index("€25.00") < fares.index("XXX 1.00")


def _trip_with_drops(sessions, drops):
    """One trip with a pinned itinerary per (currency, drop amount) in `drops`."""
    with sessions() as s:
        s.add(CurrencyRate(code="CZK", eur_per_unit=Decimal("0.04"), updated_at=T))
        t = Trip(title="Order", origin_text="A", destination_text="B")
        s.add(t)
        s.flush()
        for n, (currency, drop) in enumerate(drops):
            it = Itinerary(trip_id=t.id, fingerprint=f"drop-{n}", depart_at=T, arrive_at=T, duration_min=60,
                           pinned=True)
            it.fares.append(Fare(source="x", latest_price=Decimal("10"), seen_price=Decimal("10") + drop,
                                 currency=currency, latest_captured_at=T))
            s.add(it)
        s.commit()
        return t.id


def test_the_list_drop_is_the_largest_eur_value(sessions):
    # CZK 100 is EUR 4.00, EUR 10 is EUR 10.00: the EUR drop wins although its number is smaller
    trip_id = _trip_with_drops(sessions, [("CZK", Decimal("100")), ("EUR", Decimal("10"))])
    with sessions() as s:
        assert drops_by_trip(s)[trip_id] == ("EUR", Decimal("10"))


def test_a_drop_with_no_rate_comes_after_the_drops_with_a_rate(sessions):
    trip_id = _trip_with_drops(sessions, [("XXX", Decimal("500")), ("CZK", Decimal("100"))])
    with sessions() as s:
        assert drops_by_trip(s)[trip_id] == ("CZK", Decimal("100"))


def test_the_list_shows_the_eur_drop(sessions, trip):  # noqa: F811
    client, _, _ = trip
    _trip_with_drops(sessions, [("CZK", Decimal("100")), ("EUR", Decimal("10"))])
    html = client.get("/").text
    assert "price dropped €10" in html
    assert "price dropped CZK" not in html
