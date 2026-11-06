"""The trips list shows a return trip under its outbound trip, with the journey total (#341)."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Fare, Itinerary, Trip
from tests.test_trips_list import _client

T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _offer(trip: Trip, fp: str, price: str, currency: str = "EUR") -> Itinerary:
    it = Itinerary(trip=trip, fingerprint=fp, depart_at=T, arrive_at=T, duration_min=60)
    it.fares.append(Fare(source="x", latest_price=Decimal(price), currency=currency, latest_captured_at=T))
    return it


def _seed(engine, return_price="30.00", return_currency="EUR", return_offer=True):
    with Session(engine) as s:
        early = Trip(title="Early", origin_text="X", destination_text="Y", date_from=date(2026, 11, 1))
        out = Trip(title="Berlin", origin_text="Utrecht", destination_text="Berlin", date_from=date(2026, 12, 1))
        late = Trip(title="Late", origin_text="P", destination_text="Q", date_from=date(2026, 12, 10))
        s.add_all([early, out, late])
        s.flush()
        ret = Trip(title="Berlin (return)", origin_text="Berlin", destination_text="Utrecht",
                   return_of_id=out.id)  # no date: made later, sorted last by date
        s.add(ret)
        s.add(_offer(out, "o1", "45.50"))
        s.add(_offer(early, "e1", "10.00"))
        if return_offer:
            s.add(_offer(ret, "r1", return_price, return_currency))
        s.commit()


def test_the_return_trip_follows_its_outbound_trip(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/").text
    order = [html.index(t) for t in ("Early", "Berlin</td>", "Return of Berlin", "Late")]
    assert order == sorted(order)


def test_the_journey_total_is_the_sum_of_the_two_best_prices(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/").text
    assert "Journey total: EUR 75.50" in html


def test_no_total_without_a_return_offer(engine, monkeypatch):
    _seed(engine, return_offer=False)
    html = _client(monkeypatch).get("/").text
    assert "Journey total: no total" in html


def test_no_total_when_the_currencies_differ(engine, monkeypatch):
    _seed(engine, return_currency="USD")
    html = _client(monkeypatch).get("/").text
    assert "Journey total: no total" in html
    assert "EUR 75.50" not in html
