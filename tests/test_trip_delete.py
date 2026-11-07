"""Delete a trip from a confirm page: the offers, prices and captures go with it; a return trip stays (#416)."""

import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Capture, Fare, FarePrice, Itinerary, Leg, Trip
from tests.test_trips_list import _client

T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine) -> tuple[int, int]:
    """An outbound trip with one offer (one fare, one price) and one capture, and its return trip."""
    with Session(engine) as s:
        out = Trip(title="Berlin", origin_text="Utrecht", destination_text="Berlin", date_from=date(2026, 12, 1))
        s.add(out)
        s.flush()
        ret = Trip(title="Berlin (return)", origin_text="Berlin", destination_text="Utrecht", return_of_id=out.id)
        s.add(ret)
        cap = Capture(trip_id=out.id, captured_at=T, source="x", raw_gz=None)
        s.add(cap)
        s.flush()
        it = Itinerary(trip=out, fingerprint="o1", depart_at=T, arrive_at=T, duration_min=60)
        it.legs.append(Leg(seq=0, mode="train", from_name="Utrecht", to_name="Berlin", depart_at=T, arrive_at=T,
                           depart_offset_min=0, arrive_offset_min=0))
        fare = Fare(source="x", latest_price=Decimal("45.50"), currency="EUR", latest_captured_at=T)
        fare.prices.append(FarePrice(price=Decimal("45.50"), currency="EUR", captured_at=T, capture_id=cap.id))
        it.fares.append(fare)
        s.add(it)
        s.commit()
        return out.id, ret.id


def _csrf(client, path: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _count(engine, model, trip_id: int | None = None) -> int:
    with Session(engine) as s:
        q = select(func.count(model.id))
        if trip_id is not None:
            q = q.where(model.trip_id == trip_id)
        return s.scalar(q)


def test_the_confirm_page_shows_the_title_and_the_counts(engine, monkeypatch):
    out_id, _ = _seed(engine)
    html = _client(monkeypatch).get(f"/trips/{out_id}/delete").text
    assert "Delete the trip Berlin with 1 itineraries and 1 captures? This cannot be undone." in html


def test_the_edit_page_links_to_the_confirm_page(engine, monkeypatch):
    out_id, _ = _seed(engine)
    html = _client(monkeypatch).get(f"/trips/{out_id}/edit").text
    assert f'href="/trips/{out_id}/delete"' in html


def test_the_confirm_page_of_an_unknown_trip_is_404(engine, monkeypatch):
    _seed(engine)
    assert _client(monkeypatch).get("/trips/9999/delete").status_code == 404


def test_the_delete_removes_the_trip_with_its_offers_prices_and_captures(engine, monkeypatch):
    out_id, _ = _seed(engine)
    c = _client(monkeypatch)
    r = c.post(f"/trips/{out_id}/delete", data={"csrf_token": _csrf(c, f"/trips/{out_id}/delete")},
               follow_redirects=False)
    assert r.status_code == 303
    assert c.get(f"/trips/{out_id}").status_code == 404
    assert f"/trips/{out_id}" not in c.get("/").text
    assert _count(engine, Itinerary, out_id) == 0
    assert _count(engine, Capture, out_id) == 0
    with Session(engine) as s:
        assert s.scalar(select(func.count(Fare.id))) == 0
        assert s.scalar(select(func.count(FarePrice.id))) == 0
        assert s.scalar(select(func.count(Leg.id))) == 0


def test_the_return_trip_stays_unlinked(engine, monkeypatch):
    out_id, ret_id = _seed(engine)
    c = _client(monkeypatch)
    c.post(f"/trips/{out_id}/delete", data={"csrf_token": _csrf(c, f"/trips/{out_id}/delete")})
    with Session(engine) as s:
        ret = s.get(Trip, ret_id)
        assert ret is not None
        assert ret.return_of_id is None


def test_a_post_without_the_csrf_token_is_403_and_the_trip_stays(engine, monkeypatch):
    out_id, _ = _seed(engine)
    c = _client(monkeypatch)
    assert c.post(f"/trips/{out_id}/delete", data={"csrf_token": "wrong"}).status_code == 403
    assert _count(engine, Trip) == 2


def test_no_login_goes_to_the_login_page_and_the_trip_stays(engine, monkeypatch):
    out_id, _ = _seed(engine)
    monkeypatch.setenv("OWNER_PASSWORD_HASH", "")
    c = TestClient(app)
    r = c.post(f"/trips/{out_id}/delete", data={"csrf_token": "x"}, follow_redirects=False)
    assert r.status_code in (303, 307) and "/login" in r.headers["location"]
    assert _count(engine, Trip) == 2
