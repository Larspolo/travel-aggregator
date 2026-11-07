"""Deleting a middle trip of a journey keeps the journey one sequence: the next trip links to the previous one (#563)."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_trip_delete import _csrf
from tests.test_trips_list import _client


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _chain(engine, count=4) -> list[int]:
    """A journey of `count` trips: each trip is the return trip of the one before it."""
    ids = []
    with Session(engine) as s:
        previous = None
        for n in range(count):
            trip = Trip(title=f"Leg {n + 1}", origin_text="Utrecht", destination_text="Berlin",
                        date_from=date(2026, 12, 1 + n), return_of_id=previous)
            s.add(trip)
            s.flush()
            ids.append(trip.id)
            previous = trip.id
        s.commit()
    return ids


def _sequence(engine) -> list[int]:
    """The ids of the trips in the order of the journey: the head first, each one's return trip after it."""
    with Session(engine) as s:
        trips = s.query(Trip).all()
        following = {t.return_of_id: t.id for t in trips if t.return_of_id is not None}
        head = [t.id for t in trips if t.return_of_id is None]
        order, current = [], head[0] if len(head) == 1 else None
        while current is not None:
            order.append(current)
            current = following.get(current)
        return order


def _delete(monkeypatch, trip_id):
    c = _client(monkeypatch)
    r = c.post(f"/trips/{trip_id}/delete", data={"csrf_token": _csrf(c, f"/trips/{trip_id}/delete")},
               follow_redirects=False)
    assert r.status_code == 303


def test_deleting_the_second_trip_links_the_third_to_the_first(engine, monkeypatch):
    first, second, third, fourth = _chain(engine)
    _delete(monkeypatch, second)
    assert _sequence(engine) == [first, third, fourth]


def test_deleting_the_first_trip_keeps_the_chain_of_the_others(engine, monkeypatch):
    first, second, third, fourth = _chain(engine)
    _delete(monkeypatch, first)
    assert _sequence(engine) == [second, third, fourth]


def test_deleting_the_last_trip_keeps_the_others_as_they_were(engine, monkeypatch):
    first, second, third, fourth = _chain(engine)
    _delete(monkeypatch, fourth)
    assert _sequence(engine) == [first, second, third]
