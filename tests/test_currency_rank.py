"""The fares in other currencies rank by their EUR value (#385)."""

import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import CurrencyRate, Fare, Itinerary
from app.ranking import Breakdown, format_breakdown, in_eur
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

FLAT = {"hour_markup": "0", "transfer_markup": "0"}  # the times do not count: only the price ranks


def _costs(page):
    return re.findall(r'<[a-z]+ class="breakdown">([^<]*)', page)


def _setup(client, auth, trip_id, sessions, currency="CHF", rate="1.07"):
    """offer (472 min) gets CHF 120, direct (240 min) gets EUR 125."""
    ingest(client, auth, trip_id, [offer("89.90"), direct("125.00")])
    with sessions() as s:
        its = {i.duration_min: i for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}
        for f in s.scalars(select(Fare).where(Fare.itinerary_id == its[472].id)):
            f.currency, f.latest_price = currency, Decimal("120.00")
        if rate:
            s.add(CurrencyRate(code=currency, eur_per_unit=Decimal(rate), updated_at=datetime.now(timezone.utc)))
        s.commit()
        return its[472].id, its[240].id


def test_eur_value_ranks(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    a, b = _setup(client, auth, trip_id, sessions)
    costs = _costs(client.get(f"/trips/{trip_id}", params=FLAT).text)
    assert costs[0].startswith("€125")
    assert costs[1].startswith("CHF 120 (€128.40) price")
    compare = _costs(client.get(f"/trips/{trip_id}/compare", params={**FLAT, "it": [b, a]}).text)
    assert [c.strip() for c in compare] == [c.strip() for c in costs]


def test_cheapest_and_price_sort_use_eur(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    page = client.get(f"/trips/{trip_id}", params={**FLAT, "sort": "price"}).text
    costs = _costs(page)
    assert costs[0].startswith("€125")  # CHF 120 = €128.40 is more than €125
    row_eur = page[:page.index("CHF 120 (")]
    assert "cheapest" in row_eur


def test_no_rate(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions, currency="CZK", rate=None)
    r = client.get(f"/trips/{trip_id}", params=FLAT)
    assert r.status_code == 200
    costs = _costs(r.text)
    assert costs[0].startswith("€125") and costs[1].startswith("no rate for CZK")
    assert 'href="/rates"' in r.text


def test_breakdown_text():
    b = Breakdown(price=Decimal("128.40"), time_cost=Decimal("10"), transfer_cost=Decimal(0), total=Decimal("138.40"))
    assert format_breakdown(in_eur(b, Decimal("120"), "CHF", Decimal("128.40"))) == \
        "CHF 120 (€128.40) price + €10 time = €138.40"
    assert format_breakdown(in_eur(b, Decimal("128.40"), "EUR", Decimal("128.40"))) == \
        "€128.40 price + €10 time = €138.40"
    assert format_breakdown(in_eur(b, Decimal("1"), "CZK", None)) == "no rate for CZK"
