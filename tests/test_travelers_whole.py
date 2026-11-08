"""The whole feature of epic #761 (#1029): a capture for 2 adults of each source with a group price goes through the
ingest API and ranks by the price per traveler on the trip page and the compare page."""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import CurrencyRate, Itinerary, Trip

FIX = Path(__file__).parent / "fixtures"
CASES = [("bahn.de", "fahrplan-amsterdam-berlin-2-adults.json"),
         ("nsinternational.com", "search-amsterdam-berlin-2-adults.json"),
         ("flixbus.com", "search-2-adults.json"),
         ("kiwi.com", "search-amsterdam-zurich-2-adults.json")]
FLAT = {"hour_markup": "0", "transfer_markup": "0"}  # only the price ranks
GROUP = re.compile(r"^(?:€|[A-Z]{3} )[\d.,]+ for 2 travelers \(€([\d.,]+)\) price = €([\d.,]+)$")


@pytest.fixture
def setup(sessions):
    """A client, a token and a trip for 2 travelers and a trip for 1, with no places and no date (all match)."""
    with sessions() as s:
        token = tokens.create(s, "test")
        s.add(CurrencyRate(code="GBP", eur_per_unit=Decimal("1.15"), updated_at=datetime(2026, 11, 1, tzinfo=UTC)))
        two, one = Trip(title="For 2", travelers=2), Trip(title="For 1", travelers=1)
        s.add_all([two, one])
        s.commit()
        ids = two.id, one.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, ids
    app.dependency_overrides.pop(require_login, None)


def _ingest(client, auth, trip_id, source, name):
    raw = json.loads((FIX / source / name).read_text(encoding="utf-8"))
    r = client.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": source,
                                                       "captured_at": "2026-11-08T08:11:44Z", "raw": raw})
    assert r.status_code < 300, r.text


def _costs(page):
    return [c.strip() for c in re.findall(r'<[a-z]+ class="breakdown">([^<]*)', page)]


def _per_traveler(costs):
    values = []
    for c in costs:
        m = GROUP.match(c)
        assert m, c
        assert m.group(1) == m.group(2), c  # the total is the price per traveler
        values.append(Decimal(m.group(2).replace(",", "")))
    return values


@pytest.mark.parametrize(("source", "name"), CASES)
def test_a_capture_for_2_ranks_by_the_price_per_traveler(setup, sessions, source, name):
    client, auth, (two, _) = setup
    _ingest(client, auth, two, source, name)
    page = client.get(f"/trips/{two}", params={**FLAT, "sort": "price"}).text
    costs = _costs(page)
    values = _per_traveler(costs)
    assert values and values == sorted(values)
    row = page[:page.index(costs[0])]
    assert "cheapest" in row[row.rindex("<tr"):]  # the cheapest fare has the lowest price per traveler
    with sessions() as s:
        ids = s.scalars(select(Itinerary.id).where(Itinerary.trip_id == two)).all()
    compare = _costs(client.get(f"/trips/{two}/compare", params={**FLAT, "it": ids}).text)
    assert sorted(_per_traveler(compare)) == values


@pytest.mark.parametrize(("source", "name"), CASES)
def test_a_capture_for_2_in_a_trip_for_1_shows_the_warning(setup, source, name):
    client, auth, (_, one) = setup
    _ingest(client, auth, one, source, name)
    assert "These offers are for 2 travelers; the trip has 1" in client.get(f"/trips/{one}/captures").text
