"""The sort links and the parameter `sort` of the trips list `/` (#1973)."""

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Fare, Itinerary, Trip

PASSWORD = "pw"
T = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def _offer(trip: Trip, price: str) -> Itinerary:
    it = Itinerary(trip=trip, fingerprint=f"fp-{price}", depart_at=T, arrive_at=T, duration_min=60)
    it.fares.append(Fare(source="x", latest_price=Decimal(price), currency="EUR", latest_captured_at=T))
    return it


@pytest.fixture
def client(sessions, monkeypatch):
    with Session(sessions.kw["bind"]) as s:
        a = Trip(title="Zug trip", origin_text="Utrecht", destination_text="Zürich", tags_text="work")
        b = Trip(title="Bern trip", origin_text="Utrecht", destination_text="Bern")
        c = Trip(title="Oslo trip", origin_text="Utrecht", destination_text="Oslo")
        d = Trip(title="Basel trip", origin_text="Utrecht", destination_text="Zürich", tags_text="work",
                 status="archived")
        s.add_all([a, b, c, d, _offer(a, "90.00"), _offer(b, "40.00")])
        s.flush()
        s.add_all([Capture(trip_id=a.id, source="x", captured_at=T),
                   Capture(trip_id=c.id, source="x", captured_at=datetime(2026, 12, 5, tzinfo=UTC)),
                   Capture(trip_id=b.id, source="x", captured_at=datetime(2026, 11, 1, tzinfo=UTC))])
        s.commit()
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    cl = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', cl.get("/login").text).group(1)
    cl.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return cl


def _order(html: str) -> list[str]:
    return re.findall(r">(\w+ trip)</a></h2>", html)


def test_sort_by_capture_and_price(client):
    assert _order(client.get("/", params={"sort": "capture"}).text) == ["Oslo trip", "Zug trip", "Bern trip"]
    assert _order(client.get("/", params={"sort": "price"}).text) == ["Bern trip", "Zug trip", "Oslo trip"]
    assert _order(client.get("/", params={"sort": "title"}).text) == ["Bern trip", "Oslo trip", "Zug trip"]


def test_unknown_sort_gives_the_default_order(client):
    default = _order(client.get("/").text)
    r = client.get("/", params={"sort": "nonsense"})
    assert r.status_code == 200 and _order(r.text) == default
    assert 'aria-current="true">Date</a>' in r.text
    assert client.get("/", params={"sort": "x" * 21}).status_code == 422


def test_links_keep_the_search_tag_and_archive(client):
    html = client.get("/", params={"archived": 1, "q": "zur", "tag": "work", "sort": "price"}).text
    nav = re.search(r'<nav class="trip-sort".*?</nav>', html, re.S).group(0)
    assert _order(html) == ["Basel trip"] and nav.count("archived=1&amp;q=zur&amp;tag=work&amp;sort=") == 4
    html = client.get("/", params={"q": "zur", "tag": "work", "sort": "price"}).text
    nav = re.search(r'<nav class="trip-sort".*?</nav>', html, re.S).group(0)
    assert nav.count("q=zur&amp;tag=work&amp;sort=") == 4
    assert 'href="/?q=zur&amp;tag=work&amp;sort=price" aria-current="true"' in nav
    assert '<input type="hidden" name="sort" value="price">' in html
