"""The trips list hides the archived trips; `?archived=1` shows only them (#487)."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_trips_list import _client


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine, statuses: dict[str, str]):
    with Session(engine) as s:
        for title, status in statuses.items():
            s.add(Trip(title=title, origin_text="A", destination_text="B", date_from=date(2026, 12, 1),
                       status=status))
        s.commit()


def test_the_list_hides_the_archived_trips_and_links_to_them(engine, monkeypatch):
    _seed(engine, {"Alpha plan": "planning", "Beta booked": "booked", "Gamma old": "archived"})
    html = _client(monkeypatch).get("/").text
    assert "Alpha plan" in html
    assert "Beta booked" in html
    assert "Gamma old" not in html
    assert "Archived trips (1)" in html


def test_archived_view_shows_only_the_archived_trips(engine, monkeypatch):
    _seed(engine, {"Alpha plan": "planning", "Beta booked": "booked", "Gamma old": "archived"})
    html = _client(monkeypatch).get("/?archived=1").text
    assert "Archived trips</h1>" in html
    assert "Gamma old" in html
    assert "Alpha plan" not in html
    assert "Beta booked" not in html


def test_no_archived_link_without_archived_trips(engine, monkeypatch):
    _seed(engine, {"Alpha plan": "planning"})
    html = _client(monkeypatch).get("/").text
    assert "Archived trips" not in html


def test_a_return_trip_follows_the_status_of_its_archived_outbound_trip(engine, monkeypatch):
    with Session(engine) as s:
        out = Trip(title="Out arch", origin_text="A", destination_text="B", date_from=date(2026, 12, 1),
                   status="archived")
        s.add(out)
        s.flush()
        s.add(Trip(title="Ret plan", origin_text="B", destination_text="A", return_of_id=out.id,
                   status="planning"))
        s.commit()
    client = _client(monkeypatch)
    main = client.get("/").text
    assert "Out arch" not in main
    assert "Ret plan" not in main
    archived = client.get("/?archived=1").text
    assert "Out arch" in archived
    assert "Ret plan" in archived
