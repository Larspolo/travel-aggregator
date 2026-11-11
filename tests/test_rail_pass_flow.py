"""The whole rail pass flow (#2269, epic #2263): a train fixture and a bus fixture on one trip; a pass on /passes
covers the train fare on the trip page, and deleting the pass gives the train fare its price back."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app import tokens
from app.models import RailPass, Trip
from app.parsers.flixbus import FlixbusParser
from app.web.pages import money
from tests.test_rail_pass_page import client, _token  # noqa: F401  (client is a fixture)

BAHN = Path(__file__).parent / "fixtures" / "bahn.de"
FLIXBUS = Path(__file__).parent / "fixtures" / "flixbus.com"
PRICE_PART = re.compile(r"€[\d.,]+ price\b")  # a breakdown part of a fare price, e.g. "€45 price"


def parse_bus():
    raw = json.loads((FLIXBUS / "search-amsterdam-berlin.json").read_text(encoding="utf-8"))
    return FlixbusParser().parse(raw).offers


def _post(c, token, trip_id, source, raw):
    body = {"trip_id": trip_id, "source": source, "parser_version": "1.0.0",
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = c.post("/api/ingest", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


@pytest.fixture
def trip(sessions, client):  # noqa: F811
    """A trip with one train fixture and one bus fixture, and the owner's token."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Berlin")
        s.add(t)
        s.commit()
        trip_id = t.id
    raw_train = json.loads((BAHN / "fahrplan-amsterdam-berlin.json").read_text(encoding="utf-8"))
    raw_bus = json.loads((FLIXBUS / "search-amsterdam-berlin.json").read_text(encoding="utf-8"))
    _post(client, token, trip_id, "bahn.de", raw_train)
    _post(client, token, trip_id, "flixbus.com", raw_bus)
    return trip_id


def _save_pass(c, name="Interrail"):
    """Add a pass that covers the whole winter, with no carrier limit."""
    r = c.post("/passes", data={"id": "", "name": name, "first_day": "2026-11-01", "last_day": "2027-03-31",
                                "day_cost": "40.00", "carriers": "", "csrf_token": _token(c)},
               follow_redirects=False)
    assert r.status_code == 303


def test_the_pass_covers_the_train_fare_and_deleting_it_restores_the_price(client, sessions, trip):  # noqa: F811
    _save_pass(client)
    with sessions() as s:
        pass_id = s.query(RailPass).filter(RailPass.name == "Interrail").one().id
    path = f"/trips/{trip}/edit"
    r = client.post(path, data={"title": "Amsterdam – Berlin", "travelers": "1", "status": "planning",
                                "notes": "", "rail_pass_id": str(pass_id), "csrf_token": _token(client, path)},
                    follow_redirects=False)
    assert r.status_code == 303

    page = client.get(f"/trips/{trip}").text
    assert "pass Interrail" in page  # the train fare
    for offer in parse_bus():  # the bus fare keeps its price
        assert money(Decimal(offer.price_amount).quantize(Decimal("0.01")), offer.price_currency) in page

    r = client.post(f"/passes/{pass_id}/delete", data={"csrf_token": _token(client)}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(f"/trips/{trip}").text
    assert "pass Interrail" not in page
    assert PRICE_PART.search(page)  # the train fare shows its price again
