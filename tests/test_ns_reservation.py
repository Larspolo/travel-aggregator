"""The NS International parser and mandatory reservations (#1626)."""
import json
from pathlib import Path

from app.parsers.ns import NsParser

FIXTURE = Path(__file__).parent / "fixtures" / "nsinternational.com" / "search-amsterdam-wien-nightjet.json"


def test_nightjet_payload_has_no_reservation_status():
    raw = json.loads(FIXTURE.read_text())
    for conn in raw["response"]["data"]["travelOffers"]:
        assert all(o.get("globalReservationStatus") is None for o in conn["offers"])


def test_nightjet_legs_give_no_reservation():
    result = NsParser().parse(json.loads(FIXTURE.read_text()))
    assert result.offers and not result.errors
    assert all(leg.reservation is None for o in result.offers for leg in o.legs)


def test_offer_with_no_price_is_skipped():
    raw = json.loads(FIXTURE.read_text())
    priced = sum(o.get("totalPrice") is not None for c in raw["response"]["data"]["travelOffers"] for o in c["offers"])
    assert len(NsParser().parse(raw).offers) == priced
