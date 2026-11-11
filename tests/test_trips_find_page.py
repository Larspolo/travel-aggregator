"""The trips list and the archive have a search field (#1221)."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_trips_list import _client


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine):
    with Session(engine) as s:
        for title, dest, status in (("Work trip", "Zürich", "planning"), ("Paris weekend", "Paris", "planning"),
                                    ("Old Zürich", "Zürich", "archived"), ("Old Rome", "Rome", "archived")):
            s.add(Trip(title=title, origin_text="Amsterdam", destination_text=dest, date_from=date(2026, 12, 1),
                       status=status))
        s.commit()


def test_a_text_shows_only_the_matching_trips(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/", params={"q": "zur"}).text
    assert "Work trip" in html and "Paris weekend" not in html
    assert "In the archive (1)" in html and "Old Zürich" in html and "Old Rome" not in html
    assert 'name="q" value="zur"' in html and "Archived trips (2)" in html


def test_the_archive_shows_only_the_matching_archived_trips(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/", params={"archived": "1", "q": "zur"}).text
    assert "Old Zürich" in html and "Old Rome" not in html and "Work trip" not in html
    assert '<input type="hidden" name="archived" value="1">' in html


def test_no_match_shows_an_empty_state_with_a_link(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/", params={"q": "xyz"}).text
    assert "No trip matches &#34;xyz&#34;." in html or 'No trip matches "xyz".' in html
    assert '<a class="btn" href="/">Show all trips</a>' in html


def test_the_text_is_escaped(engine, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch).get("/", params={"q": "<script>"}).text
    assert "<script>" not in html.split("</head>", 1)[1].replace("<script src", "")
    assert "&lt;script&gt;" in html
