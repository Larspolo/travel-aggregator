"""The trip page lists the search status of each source (#967): the newest capture, or "not searched yet"."""

import html
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.parsers as parsers
from app.auth import require_login
from app.coverage import trip_coverage
from app.main import app
from app.models import Capture, Trip


@pytest.fixture
def trips(sessions):
    """A client with the owner login, a trip Amsterdam → Berlin with two bahn.de captures, and another trip."""
    now = datetime.now(timezone.utc)
    with sessions() as s:
        t = Trip(title="Amsterdam – Berlin", origin_text="Amsterdam", destination_text="Berlin",
                 date_from=date(2026, 12, 1))
        other = Trip(title="Other", origin_text="Amsterdam", destination_text="Berlin", date_from=date(2026, 12, 1))
        s.add_all([t, other])
        s.flush()
        s.add_all([Capture(trip_id=t.id, source="bahn.de", captured_at=now - timedelta(hours=30), offer_count=3),
                   Capture(trip_id=t.id, source="bahn.de", captured_at=now - timedelta(hours=2), offer_count=14),
                   Capture(trip_id=other.id, source="nsinternational.com", captured_at=now, offer_count=5),
                   Capture(trip_id=other.id, source="bahn.de", captured_at=now, offer_count=99)])
        s.commit()
        ids = t.id, other.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), ids
    app.dependency_overrides.pop(require_login, None)


def _items(page: str) -> list[str]:
    block = re.search(r'<ul class="search-links"[^>]*>(.*?)</ul>', page, re.S).group(1)
    return [html.unescape(i) for i in re.findall(r"<li>(.*?)</li>", block, re.S)]


def test_the_list_shows_the_newest_capture_and_the_sources_not_searched(trips):
    client, (trip_id, _) = trips
    items = _items(client.get(f"/trips/{trip_id}").text)

    assert len(items) == len(parsers.all_sources())
    assert items[0].startswith("bahn.de: 2 h ago · 14 offers · <a href=")
    ns = next(i for i in items if i.startswith("NS International"))
    assert ns.startswith("NS International: not searched yet · <a href=")
    assert "/search/NLASC/DEBHF/20261201" in ns
    assert "kiwi.com: not searched yet" in items  # no capture and no link


def test_the_captures_of_another_trip_do_not_change_the_list(trips, sessions):
    _, (trip_id, other_id) = trips
    with sessions() as s:
        entries = {e["source"]: e for e in trip_coverage(s, s.get(Trip, trip_id))}
    assert entries["bahn.de"]["offer_count"] == 14
    assert entries["nsinternational.com"]["captured_at"] is None


def test_a_new_parser_source_shows_as_not_searched_yet(trips, monkeypatch):
    client, (trip_id, _) = trips
    original = parsers.parser_classes
    monkeypatch.setattr(parsers, "parser_classes", lambda: {**original(), "example.test": object})

    assert "example.test: not searched yet" in _items(client.get(f"/trips/{trip_id}").text)


def test_the_list_takes_one_query(trips, sessions):
    _, (trip_id, _) = trips
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        statements = []
        listener = lambda *args: statements.append(args[2])  # noqa: E731
        event.listen(s.get_bind(), "before_cursor_execute", listener)
        try:
            trip_coverage(s, trip)
        finally:
            event.remove(s.get_bind(), "before_cursor_execute", listener)
    assert len(statements) == 1
