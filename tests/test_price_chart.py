"""The SVG price chart of the history fragment (#241): app.history.chart and the page."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.history import chart
from tests.test_price_history import _add_later_price, _itinerary_id, trip  # noqa: F401

T0 = datetime(2026, 11, 1, 8, tzinfo=UTC)


@dataclass
class P:
    price: Decimal
    captured_at: datetime
    currency: str = "EUR"


@dataclass
class F:
    fare_name: str
    prices: list = field(default_factory=list)
    source: str = "bahn.de"


def test_two_captures_give_two_points_higher_price_higher():
    c = chart([F("Flex", [P(Decimal("80"), T0), P(Decimal("100"), T0 + timedelta(days=1))])])
    (line,) = c["lines"]
    a, b = line["dots"]
    assert len(line["points"].split()) == 2
    assert b["y"] < a["y"] and a["x"] < b["x"]
    assert (c["low"], c["high"]) == (Decimal("80"), Decimal("100"))
    assert isinstance(c["low"], Decimal)


def test_two_fares_give_two_lines():
    c = chart([F("A", [P(Decimal("50"), T0)]), F("B", [P(Decimal("70"), T0 + timedelta(hours=2))])])
    assert [x["name"] for x in c["lines"]] == ["bahn.de: A", "bahn.de: B"]


def test_one_capture_is_one_point_in_the_middle():
    c = chart([F("A", [P(Decimal("50"), T0)])], width=200, height=80)
    assert c["lines"][0]["dots"][0]["x"] == 100 and c["lines"][0]["dots"][0]["y"] == 40
    assert chart([])["lines"] == []


def test_page_has_svg_with_polyline(trip, sessions):  # noqa: F811
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    _add_later_price(sessions, it, "85.00")
    r = client.get(f"/trips/{trip_id}/itineraries/{it}/history", headers={"HX-Request": "true"})  # the fragment
    assert r.text.count("<svg") == 1 and r.text.count("<polyline") == 1 and r.text.count("<circle") == 2
    assert "low EUR 85.00" in r.text and "high EUR 89.90" in r.text
    assert r.text.index("<svg") < r.text.index("<table")
