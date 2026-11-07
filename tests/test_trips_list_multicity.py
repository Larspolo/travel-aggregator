"""The trips list shows the trips of a multi-city journey together, with one total (#561)."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Fare, Itinerary, Trip
from tests.test_trips_list import _client

T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)
TITLES = ["Leg Amsterdam", "Leg Berlin", "Leg Prague", "Leg Vienna"]


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine, prices=("10.00", "20.00", "30.50", "40.00"), first_status="planning"):
    with Session(engine) as s:
        s.add(Trip(title="Other trip", origin_text="X", destination_text="Y", date_from=date(2026, 11, 1)))
        prev = None
        for i, (title, price) in enumerate(zip(TITLES, prices)):
            t = Trip(title=title, origin_text="A", destination_text="B", date_from=date(2026, 12, 20 - i),
                     status=first_status if i == 0 else "planning",
                     return_of_id=prev.id if prev else None)
            s.add(t)
            s.flush()
            if price is not None:
                it = Itinerary(trip=t, fingerprint=f"f{i}", depart_at=T, arrive_at=T, duration_min=60)
                it.fares.append(Fare(source="x", latest_price=Decimal(price), currency="EUR", latest_captured_at=T))
                s.add(it)
            prev = t
        s.commit()


def test_a_chain_of_four_trips_shows_in_sequence_with_the_total(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/").text
    order = [html.index(t + "</td>") for t in TITLES]
    assert order == sorted(order)
    assert html.count("Journey price total") == 1
    assert "Journey price total: EUR 100.50" in html


def test_no_total_when_one_trip_has_no_offer(engine, monkeypatch):
    _seed(engine, prices=("10.00", None, "30.50", "40.00"))
    assert "Journey price total: no total" in _client(monkeypatch).get("/").text


def test_an_archived_first_trip_moves_all_trips_to_the_archived_list(engine, monkeypatch):
    _seed(engine, first_status="archived")
    c = _client(monkeypatch)
    html = c.get("/").text
    assert not any(t in html for t in TITLES)
    archived = c.get("/?archived=1").text
    assert all(t in archived for t in TITLES)
