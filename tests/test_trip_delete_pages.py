"""Each GET page of a deleted trip is 404, and the API lists no deleted trip (#436, epic #415)."""

import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app import tokens
from app.main import app
from app.models import Capture, Fare, FarePrice, Itinerary, Leg, Trip
from tests.test_trips_list import _client

T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)

# every GET page under /trips/{trip_id}; a new one must be added here (the test below checks it)
TRIP_PAGES = [
    "/trips/{trip_id}",
    "/trips/{trip_id}/edit",
    "/trips/{trip_id}/delete",
    "/trips/{trip_id}/compare",
    "/trips/{trip_id}/itineraries/{itinerary_id}/history",
    "/trips/{trip_id}/offers/new",
    "/trips/{trip_id}/captures",
    "/trips/{trip_id}/export.json",
    "/trips/{trip_id}/export.csv",
]


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine) -> tuple[int, int, int]:
    """An outbound trip with one itinerary (one fare, one price) and one capture, and its return trip."""
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
        return out.id, ret.id, it.id


def _csrf(client, path: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _delete(client, trip_id: int) -> None:
    path = f"/trips/{trip_id}/delete"
    r = client.post(path, data={"csrf_token": _csrf(client, path)}, follow_redirects=False)
    assert r.status_code == 303


@pytest.mark.parametrize("template", TRIP_PAGES)
def test_each_page_of_a_deleted_trip_is_404(engine, monkeypatch, template):
    out_id, _, it_id = _seed(engine)
    c = _client(monkeypatch)
    _delete(c, out_id)
    path = template.format(trip_id=out_id, itinerary_id=it_id)
    assert c.get(path).status_code == 404


def _app_get_paths() -> set[str]:
    """The full paths of the GET routes of the app: FastAPI wraps each included router, so walk them."""
    paths = set()
    for wrapper in app.routes:
        inner = getattr(wrapper, "original_router", None)
        if inner is None:
            continue
        prefix = getattr(wrapper.include_context, "prefix", "") or ""
        for r in inner.routes:
            if isinstance(r, APIRoute) and "GET" in r.methods:
                paths.add(prefix + r.path)
    return paths


def test_every_get_route_under_a_trip_is_in_the_list():
    found = {p for p in _app_get_paths() if p.startswith("/trips/{trip_id}")}
    assert found, "no GET route under /trips/{trip_id} found"
    missing = found - set(TRIP_PAGES)
    assert not missing, f"add these to TRIP_PAGES: {sorted(missing)}"


def test_api_trips_does_not_list_the_deleted_trip(engine, sessions, monkeypatch):
    out_id, ret_id, _ = _seed(engine)
    with sessions() as s:
        token = tokens.create(s, "test")
    c = _client(monkeypatch)
    _delete(c, out_id)
    r = c.get("/api/trips", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert out_id not in ids
    assert ret_id in ids
