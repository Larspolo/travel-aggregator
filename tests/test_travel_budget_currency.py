"""A paid price in another currency counts in EUR in the travel budget; a price with no rate is named (#2374, #2375, #2376)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import CurrencyRate, Itinerary, TravelBudget, Trip
from tests.test_spend_page import add, client, text  # noqa: F401  (client is a fixture)
from tests.test_travel_budget_trip import _it

NOTE = "(prices with no rate are not counted)"


def _journeys(sessions, usd=True, xyz=False):
    """A EUR journey of 1000.00 and a 100.00 journey in USD (or in XYZ with no rate) in 2026."""
    with sessions() as s:
        add(s, 0, 2026, "train", 600, "1000.00")
        add(s, 1, 2026, "bus", 60, "100.00")
        it = s.scalars(select(Itinerary).where(Itinerary.fingerprint == "f2026-1")).one()
        it.booked_currency = "XYZ" if xyz else "USD"
        s.add(CurrencyRate(code="USD", eur_per_unit=Decimal("0.90"), updated_at=datetime.now(UTC)))
        s.commit()


def _budget(sessions, amount="1200"):
    with sessions() as s:
        s.add(TravelBudget(year=2026, amount=Decimal(amount), updated_at=datetime.now(UTC)))
        s.commit()


def _trip(sessions):
    with sessions() as s:
        trip = Trip(title="Amsterdam → Berlin", origin_text="Amsterdam", destination_text="Berlin",
                    status="planning", date_from=date(2026, 12, 20))
        trip.itineraries = [_it(9, [("210.00", "EUR")])]  # the trip page shows the budget line with an offer
        s.add(trip)
        s.commit()
        return trip.id


def test_a_paid_price_in_a_currency_with_a_rate_counts_in_eur_on_the_budget_page(client, sessions):  # noqa: F811
    _journeys(sessions)
    _budget(sessions)
    page = text(client.get("/upcoming/years").text)
    assert "€1,090.00 of €1,200.00 · €110.00 left" in page  # 1000.00 + 100.00 USD × 0.90
    assert NOTE not in page


def test_a_paid_price_in_a_currency_with_a_rate_counts_in_eur_on_the_trip_page(client, sessions):  # noqa: F811
    _journeys(sessions)
    _budget(sessions)
    page = text(client.get(f"/trips/{_trip(sessions)}").text)
    assert "€110.00 left of the budget of 2026" in page
    assert NOTE not in page


def test_a_price_with_no_rate_is_named_on_the_budget_page(client, sessions):  # noqa: F811
    _journeys(sessions, xyz=True)
    _budget(sessions)
    page = text(client.get("/upcoming/years").text)
    assert "€1,000.00 of €1,200.00 · €200.00 left" in page
    assert "1 price in XYZ has no rate" in page and NOTE in page


def test_a_price_with_no_rate_is_noted_on_the_trip_page(client, sessions):  # noqa: F811
    _journeys(sessions, xyz=True)
    _budget(sessions)
    page = text(client.get(f"/trips/{_trip(sessions)}").text)
    assert "€200.00 left of the budget of 2026 " + NOTE in page


def test_all_prices_in_eur_have_no_note_on_the_trip_page(client, sessions):  # noqa: F811
    with sessions() as s:
        add(s, 0, 2026, "train", 600, "1000.00")
        s.commit()
    _budget(sessions)
    page = text(client.get(f"/trips/{_trip(sessions)}").text)
    assert "€200.00 left of the budget of 2026" in page
    assert NOTE not in page
