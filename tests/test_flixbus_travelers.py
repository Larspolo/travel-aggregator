"""A Flixbus search for 2 adults ranks by the price per traveler (#1026), as bahn.de does (#767).

The fixture is the search of #768 for 2 adults: `price.total` is the price for all travelers.
"""

import json
import re
from pathlib import Path

from sqlalchemy import select

from app.models import Capture
from app.parsers import group_price
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIXTURE = Path(__file__).parent / "fixtures" / "flixbus.com" / "search-2-adults.json"
FLAT = {"hour_markup": "0", "transfer_markup": "0"}  # only the price ranks


def _costs(page):
    return [c.strip() for c in re.findall(r'<[a-z]+ class="breakdown">([^<]*)', page)]


def _ingest_fixture(client, auth, trip_id):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    r = client.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "flixbus.com",
                                                       "captured_at": "2026-11-08T08:11:44Z", "raw": raw})
    assert r.status_code < 300, r.text


def test_the_fixture_is_for_two_travelers(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id)
    with sessions() as s:
        assert s.scalar(select(Capture.travelers).where(Capture.trip_id == trip_id)) == 2


def test_the_page_shows_the_group_price_and_the_price_per_traveler(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id)
    costs = _costs(client.get(f"/trips/{trip_id}", params=FLAT).text)
    # total is the price for 2 travelers; the price per traveler is total / 2
    assert "€55.98 for 2 travelers (€27.99) price = €27.99" in costs
    assert "€59.96 for 2 travelers (€29.98) price = €29.98" in costs
    assert costs[0].endswith("= €27.99")  # the order uses the price per traveler


def test_the_source_is_a_group_price():
    assert group_price("flixbus.com")
