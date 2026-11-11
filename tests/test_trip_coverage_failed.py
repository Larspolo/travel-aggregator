"""The trip page says when the last search of a source failed (#968), not "not searched yet"."""

import html
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app
from app.models import Capture, Trip


@pytest.fixture
def trip_id(sessions):
    now = datetime.now(timezone.utc)
    with sessions() as s:
        t = Trip(title="Amsterdam – Berlin", origin_text="Amsterdam", destination_text="Berlin",
                 date_from=date(2026, 12, 1))
        s.add(t)
        s.flush()
        s.add_all([Capture(trip_id=t.id, source="bahn.de", captured_at=now - timedelta(hours=30), offer_count=3),
                   Capture(trip_id=t.id, source="bahn.de", captured_at=now - timedelta(hours=2), offer_count=0,
                           unreadable="parser error")])
        s.commit()
        tid = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield tid
    app.dependency_overrides.pop(require_login, None)


def _items(page: str) -> list[str]:
    block = re.search(r'<ul class="search-links"[^>]*>(.*?)</ul>', page, re.S).group(1)
    return [html.unescape(i) for i in re.findall(r"<li>(.*?)</li>", block, re.S)]


def test_a_failed_newest_capture_shows_last_search_failed_with_its_link(trip_id):
    page = TestClient(app).get(f"/trips/{trip_id}").text
    item = next(i for i in _items(page) if i.startswith("bahn.de"))

    assert item.startswith("bahn.de: last search failed")
    assert f'href="/trips/{trip_id}/captures?failed=1"' in item


def test_an_older_failed_capture_and_a_newer_good_one_show_the_good_status(sessions, trip_id):
    now = datetime.now(timezone.utc)
    with sessions() as s:
        s.add(Capture(trip_id=trip_id, source="bahn.de", captured_at=now, offer_count=7))
        s.commit()
    page = TestClient(app).get(f"/trips/{trip_id}").text
    item = next(i for i in _items(page) if i.startswith("bahn.de"))

    assert "· 7 offers" in item
    assert "last search failed" not in item
