"""A search on the trips list also finds the archived trips, in a section "In the archive" (#1222)."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_trips_list import _client


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine, trips):
    with Session(engine) as s:
        for title, dest, status in trips:
            s.add(Trip(title=title, origin_text="Amsterdam", destination_text=dest, date_from=date(2026, 12, 20),
                       status=status))
        s.commit()


def test_a_search_shows_the_matching_archived_trip_under_the_archive_heading(engine, monkeypatch):
    _seed(engine, [("Amsterdam → Zürich", "Zürich", "planning"), ("Zürich Christmas", "Zürich", "archived")])
    html = _client(monkeypatch).get("/", params={"q": "zur"}).text
    assert "Amsterdam → Zürich" in html and "Zürich Christmas" in html
    assert "In the archive (1)" in html
    assert html.index("Amsterdam → Zürich") < html.index("In the archive (1)") < html.index("Zürich Christmas")


def test_no_text_shows_no_archive_section(engine, monkeypatch):
    _seed(engine, [("Amsterdam → Zürich", "Zürich", "planning"), ("Zürich Christmas", "Zürich", "archived")])
    html = _client(monkeypatch).get("/").text
    assert "In the archive" not in html


def test_only_an_archived_match_shows_the_trip_and_no_empty_state(engine, monkeypatch):
    _seed(engine, [("Amsterdam → Paris", "Paris", "planning"), ("Zürich Christmas", "Zürich", "archived")])
    html = _client(monkeypatch).get("/", params={"q": "zur"}).text
    assert "Zürich Christmas" in html and "In the archive (1)" in html
    assert "No trip matches" not in html
    assert "Amsterdam → Paris" not in html
