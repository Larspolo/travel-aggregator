"""The trips list shows one card per trip and an empty state (#626)."""

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Trip

PASSWORD = "pw"
T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


def _client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _cards(html):
    return re.findall(r'<section class="card">(.*?)</section>', html, re.S)


def test_card_values(sessions, monkeypatch):
    with Session(sessions.kw["bind"]) as s:
        t = Trip(title="Berlin weekend", origin_text="Utrecht", destination_text="Berlin", status="booked",
                 date_from=date(2026, 12, 1), date_to=date(2026, 12, 5))
        it = Itinerary(trip=t, fingerprint="f1", depart_at=T, arrive_at=T, duration_min=60)
        it.fares.append(Fare(source="x", latest_price=Decimal("45.5"), currency="EUR", latest_captured_at=T))
        s.add_all([t, it, Trip(title="Empty", origin_text="A", destination_text="B")])
        s.commit()
        tid = t.id
    html = _client(monkeypatch).get("/").text
    assert "<table>" not in html and 'class="trip-grid"' in html
    cards = _cards(html)
    assert len(cards) == 2
    card = next(c for c in cards if "Berlin weekend" in c)
    assert f'<h2><a href="/trips/{tid}">Berlin weekend</a></h2>' in card
    assert 'href="#arrow-right"' not in card and "#arrow-right" in card
    assert "Utrecht" in card and "Berlin</p>" in card
    assert "2026-12-01 – 2026-12-05" in card and "1 offer<" in card
    assert "<strong>€45.50</strong>" in card
    assert '<span class="chip good">booked</span>' in card
    assert f'href="/trips/{tid}/edit"' in card and "#pencil" in card
    empty = next(c for c in cards if "Empty" in c)
    assert "0 offers" in empty and "no offers yet" in empty


def test_empty_state(sessions, monkeypatch):
    html = _client(monkeypatch).get("/").text
    box = re.search(r'<div class="empty">(.*?)</div>\s*</div>', html, re.S).group(1)
    assert 'class="btn btn-primary" href="/trips/new"' in box and "New trip" in box
    assert 'class="trip-grid"' not in html
