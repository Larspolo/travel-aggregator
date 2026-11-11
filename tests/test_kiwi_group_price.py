"""A Kiwi.com search for 2 or more travelers ranks by the price per traveler (#1027, as bahn.de in #767).

The tests use the 2-adult fixture of Kiwi.com: a wrong rule passes all tests with the 1-adult fixtures.
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.models import Capture, CurrencyRate
from app.parsers import group_price
from app.parsers.kiwi import KiwiParser
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIXTURE = Path(__file__).parent / "fixtures" / "kiwi.com" / "search-amsterdam-zurich-2-adults.json"
FLAT = {"hour_markup": "0", "transfer_markup": "0"}  # only the price ranks


def _costs(page):
    return [c.strip() for c in re.findall(r'<[a-z]+ class="breakdown">([^<]*)', page)]


def _ingest_fixture(client, auth, trip_id):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    r = client.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "kiwi.com",
                                                       "captured_at": "2026-11-08T08:11:44Z", "raw": raw})
    assert r.status_code < 300, r.text


def test_the_fixture_is_for_two_travelers(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_fixture(client, auth, trip_id)
    with sessions() as s:
        assert s.scalar(select(Capture.travelers).where(Capture.trip_id == trip_id)) == 2


def test_the_parser_gives_two_travelers_and_a_group_price():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert KiwiParser().parse(raw).travelers == 2
    assert group_price("kiwi.com")


def test_the_trip_page_shows_the_price_per_traveler(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    with sessions() as s:
        s.add(CurrencyRate(code="GBP", eur_per_unit=Decimal("1.15"), updated_at=datetime(2026, 11, 1, tzinfo=UTC)))
        s.commit()
    _ingest_fixture(client, auth, trip_id)
    costs = _costs(client.get(f"/trips/{trip_id}", params=FLAT).text)
    # the fixture prices for 2 adults (GBP 323, 328, 333) at 1.15 EUR per GBP, per traveler half of each
    assert costs == [
        "GBP 323 for 2 travelers (€185.72) price = €185.72",
        "GBP 328 for 2 travelers (€188.60) price = €188.60",
        "GBP 333 for 2 travelers (€191.48) price = €191.48",
    ]
