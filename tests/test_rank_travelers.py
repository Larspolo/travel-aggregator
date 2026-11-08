"""The fares of a capture for 2 or more travelers rank by the price per traveler (#767).

The tests use the 2-adult fixture of bahn.de: a wrong rule passes all tests with the 1-adult fixtures.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.models import Capture, Itinerary
from app.parsers import group_price
from app.ranking import Breakdown, Weights, effective_cost, for_group, format_breakdown, in_eur, per_traveler
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

FIXTURE = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-amsterdam-berlin-2-adults.json"
FLAT = {"hour_markup": "0", "transfer_markup": "0"}  # only the price ranks


def _costs(page):
    return [c.strip() for c in re.findall(r'<[a-z]+ class="breakdown">([^<]*)', page)]


def _ingest_fixture(client, auth, trip_id, first_price=None):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if first_price is not None:
        raw["response"]["verbindungen"][0]["angebotsPreis"]["betrag"] = first_price
    r = client.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de",
                                                       "captured_at": "2026-11-08T08:11:44Z", "raw": raw})
    assert r.status_code < 300, r.text


def test_the_fixture_is_for_two_travelers(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id)
    with sessions() as s:
        assert s.scalar(select(Capture.travelers).where(Capture.trip_id == trip_id)) == 2


def test_a_group_of_180_ranks_with_90(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id, first_price=180)
    costs = _costs(client.get(f"/trips/{trip_id}", params=FLAT).text)
    assert "€180 for 2 travelers (€90) price = €90" in costs
    # the real prices of the fixture: 131.98 and 149.98 for 2 adults
    assert "€131.98 for 2 travelers (€65.99) price = €65.99" in costs
    assert "€149.98 for 2 travelers (€74.99) price = €74.99" in costs
    assert costs[0].endswith("= €65.99")  # the order uses the price per traveler


def test_the_other_parts_stay_per_person(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id, first_price=180)
    costs = _costs(client.get(f"/trips/{trip_id}", params={"hour_markup": "15", "transfer_markup": "10"}).text)
    # ICE 143 + ICE 847: 08:00 to 15:18 = 438 min (€109.50 time) and 1 transfer (€10)
    assert "€180 for 2 travelers (€90) price + €109.50 time + €10 transfers = €209.50" in costs


def test_cheapest_and_price_sort_use_the_price_per_traveler(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id)  # 113.98 for 2 = 56.99 each
    ingest(client, auth, trip_id, [offer("60.00")])  # 1 traveler: 60 is less than 113.98, more than 56.99
    page = client.get(f"/trips/{trip_id}", params={**FLAT, "sort": "price"}).text
    costs = _costs(page)
    assert costs[0] == "€113.98 for 2 travelers (€56.99) price = €56.99"
    assert costs[1] == "€60 price = €60"
    row = page[:page.index("€113.98 for 2 travelers")]
    assert "cheapest" in row[row.rindex("<tr"):]


def test_the_compare_page_shows_the_same_breakdown(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id, first_price=180)
    with sessions() as s:
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == trip_id).order_by(Itinerary.depart_at)).all()
    trip_costs = _costs(client.get(f"/trips/{trip_id}", params=FLAT).text)
    compare = _costs(client.get(f"/trips/{trip_id}/compare", params={**FLAT, "it": ids}).text)
    assert compare[0] == "€180 for 2 travelers (€90) price = €90"
    assert sorted(compare) == sorted(trip_costs)


def test_one_traveler_or_no_count_keeps_the_breakdown():
    w = Weights()
    plain = effective_cost(Decimal("180"), 120, 1, w)
    for n in (None, 1):
        b = for_group(effective_cost(per_traveler(Decimal("180"), n), 120, 1, w), Decimal("180"), "EUR", n)
        assert b == plain and format_breakdown(b) == "€180 price + €30 time + €10 transfers = €220"


def test_the_price_per_traveler_rounds_to_cents():
    b = effective_cost(per_traveler(Decimal("113.97"), 2), 0, 0, Weights())
    assert b.price == Decimal("56.98")  # 56.985, half to even as _cents()


def test_a_group_price_in_another_currency():
    eur = Decimal("256.80")  # CHF 240 at 1.07
    b = effective_cost(per_traveler(eur, 2), 60, 0, Weights())
    b = for_group(in_eur(b, Decimal("240"), "CHF", eur), Decimal("240"), "CHF", 2)
    assert format_breakdown(b) == "CHF 240 for 2 travelers (€128.40) price + €15 time = €143.40"


def test_no_rate_shows_no_group():
    inf = Breakdown(price=Decimal("Infinity"), time_cost=Decimal(0), transfer_cost=Decimal(0),
                    total=Decimal("Infinity"), no_rate="CZK")
    assert format_breakdown(for_group(inf, Decimal("1000"), "CZK", 2)) == "no rate for CZK"


def test_the_sources_of_a_group_price():
    # the fixture READMEs: bahn.de and nsinternational.com give the price of the group
    assert group_price("bahn.de") and group_price("nsinternational.com")
    assert not group_price("unknown.example")
