"""The trip page marks the gone fares and ranks with the current fares (#1386)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.gone
from app.gone import GoneMark
from app.models import Fare, Itinerary, Trip
from app.ranking import Weights
from app.web.pages import best_for_weights, current_fares
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


@pytest.fixture
def gone_sparpreis(trip, sessions, monkeypatch):  # noqa: F811
    """One ICE with a gone Sparpreis of €39 and a current Flexpreis of €89, and an other ICE with only a gone fare."""
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("39.00", "ICE 1", fare="Sparpreis"), offer("89.00", "ICE 1", fare="Flexpreis"),
                               offer("49.00", "ICE 2", fare="Sparpreis")])
    with sessions() as s:
        fares = {str(f.latest_price): f.id for f in s.scalars(select(Fare))}
    at = datetime.now(timezone.utc) - timedelta(hours=2)
    marks = {fares["39.00"]: GoneMark("bahn.de", at), fares["49.00"]: GoneMark("bahn.de", at)}
    monkeypatch.setattr(app.gone, "gone_fares", lambda session, trip_ids: marks)
    return client, tid, fares, sessions


def test_current_fares():
    class F:
        def __init__(self, i):
            self.id = i
    a, b = F(1), F(2)
    assert current_fares([a, b], {1: None}) == [b]
    assert current_fares([a], {1: None}) == [a]


def test_row_shows_current_fare_and_marks_gone_fare(gone_sparpreis):
    client, tid, fares, sessions = gone_sparpreis
    page = client.get(f"/trips/{tid}").text
    with sessions() as s:
        ice1 = s.get(Fare, fares["89.00"]).itinerary_id
        ice2 = s.get(Fare, fares["49.00"]).itinerary_id
    row = page[page.index(f'id="it-{ice1}"'):]
    row = row[:row.index("</tr>")]
    assert "€89.00" in row and "€39.00" not in row
    assert "not in the last bahn.de search, 2 h ago" in page
    assert page.index(f'id="it-{ice1}"') < page.index(f'id="it-{ice2}"')
    gone_row = page[page.index(f'id="it-{ice2}"'):]
    gone_row = gone_row[:gone_row.index("</tr>")]
    assert "cheapest" not in gone_row and "best value" not in gone_row
    assert "not in the last bahn.de search" in gone_row


def test_best_for_weights_uses_current_fare(gone_sparpreis):
    client, tid, fares, sessions = gone_sparpreis
    with sessions() as s:
        it, fare, cost = best_for_weights(s, s.get(Trip, tid), Weights())
        assert fare.id == fares["89.00"]
        assert s.get(Itinerary, it.id).id == it.id


def test_days_use_current_fares(gone_sparpreis):
    client, tid, fares, sessions = gone_sparpreis
    from app.web import pages
    seen = {}
    real = pages.day_summary
    monkey = pytest.MonkeyPatch()
    monkey.setattr(pages, "day_summary", lambda rows, *a: seen.setdefault("rows", rows) and real(rows, *a))
    try:
        client.get(f"/trips/{tid}")
    finally:
        monkey.undo()
    assert {str(f.latest_price) for _, f, _ in seen["rows"]} == {"89.00"}
