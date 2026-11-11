"""The trip page shows the rest of the travel budget of the year and marks each fare over it (#2376)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models import Fare, Itinerary, Leg, TravelBudget, Trip
import re

from tests.test_spend_page import add, client, text  # noqa: F401  (client is a fixture)

DEP = datetime(2026, 12, 20, 8, tzinfo=UTC)


def _it(n, prices):
    it = Itinerary(fingerprint=f"b{n}", depart_at=DEP + timedelta(hours=n), arrive_at=DEP + timedelta(hours=n + 6),
                   duration_min=360, transfers=0, mode_summary="train")
    it.legs = [Leg(seq=0, mode="train", carrier="X", service_no=str(n), from_name="Amsterdam", to_name="Berlin",
                   depart_at=it.depart_at, depart_offset_min=60, arrive_at=it.arrive_at, arrive_offset_min=60)]
    it.fares = [Fare(source=f"s{i}", latest_price=Decimal(p), currency=c, latest_captured_at=datetime.now(UTC))
                for i, (p, c) in enumerate(prices)]
    return it


def _marked(html):
    """The prices with the mark; the list of the fares of a row repeats its main fare."""
    return set(re.findall(r"€([\d.,]+)(?:</strong>)? <span class=\"chip over-budget\">", html))


def _trip(sessions, budget="1200", paid=("1000.00", "15.80"), date_from=date(2026, 12, 20), year=2026):
    with sessions() as s:
        if budget is not None:
            s.add(TravelBudget(year=year, amount=Decimal(budget), updated_at=datetime.now(UTC)))
        for n, price in enumerate(paid):
            add(s, n, 2026, "train", 60, price)
        trip = Trip(title="Amsterdam → Berlin", origin_text="Amsterdam", destination_text="Berlin",
                    status="planning", date_from=date_from)
        trip.itineraries = [_it(1, [("210.00", "EUR")]), _it(2, [("104.50", "EUR"), ("300.00", "EUR")]),
                            _it(3, [("5.00", "XYZ")])]
        s.add(trip)
        s.commit()
        return trip.id


def test_the_rest_and_the_marks(client, sessions):  # noqa: F811
    html = client.get(f"/trips/{_trip(sessions)}").text
    assert "€184.20 left of the budget of 2026" in text(html)
    assert _marked(html) == {"210.00", "300.00"}  # not 104.50, not the fare of XYZ with no rate


def test_over_the_budget_marks_each_fare(client, sessions):  # noqa: F811
    html = client.get(f"/trips/{_trip(sessions, budget='1000')}").text
    assert "€15.80 over the budget of 2026" in text(html)
    assert _marked(html) == {"210.00", "104.50", "300.00"}  # all fares with a rate


def test_no_date_from_or_no_budget(client, sessions):  # noqa: F811
    trip_id = _trip(sessions, date_from=None)
    assert "budget-left" not in client.get(f"/trips/{trip_id}").text


def test_a_year_with_no_budget(client, sessions):  # noqa: F811
    html = client.get(f"/trips/{_trip(sessions, date_from=date(2027, 1, 5))}").text
    assert "budget-left" not in html and "over-budget" not in html


def test_the_htmx_table_keeps_the_marks(client, sessions):  # noqa: F811
    html = client.get(f"/trips/{_trip(sessions)}", headers={"HX-Request": "true"}).text
    assert _marked(html) == {"210.00", "300.00"}
