"""The trips list shows "N trips are in the past" and "Archive them" archives these trips (#1998)."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Itinerary, Leg, Trip
from tests.test_trips_list import _client


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _seed(engine) -> int:
    today = date.today()
    with Session(engine) as s:
        old = Trip(title="Ten days ago", origin_text="A", destination_text="B",
                   date_from=today - timedelta(days=12), date_to=today - timedelta(days=10), status="booked")
        s.add(old)
        s.add(Trip(title="Thirty days ago", origin_text="A", destination_text="C",
                   date_from=today - timedelta(days=30)))
        s.add(Trip(title="Next month", origin_text="A", destination_text="D", date_from=today + timedelta(days=30)))
        s.flush()
        depart = datetime.combine(today - timedelta(days=12), datetime.min.time(), timezone.utc) + timedelta(hours=8)
        leg = Leg(seq=0, mode="train", carrier="ICE", service_no="201", from_name="A", to_name="B",
                  depart_at=depart, depart_offset_min=60, arrive_at=depart + timedelta(hours=3), arrive_offset_min=60)
        old.itineraries.append(Itinerary(fingerprint="past-1", depart_at=depart, arrive_at=leg.arrive_at,
                                         duration_min=180, booked=True, booked_price=Decimal("50.00"),
                                         booked_currency="EUR", legs=[leg]))
        s.commit()
        return depart.year


def _main(html: str) -> str:
    """The page with no CSRF token and no save time, so that two loads compare."""
    return re.sub(r'data-saved-at="[^"]+"|name="csrf_token" value="[^"]+"', "", html)


def test_archive_them_moves_the_past_trips_and_keeps_upcoming_and_years(engine, monkeypatch):
    year = _seed(engine)
    c = _client(monkeypatch)
    html = c.get("/").text
    assert "2 trips are in the past." in html
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    before = [_main(c.get(u).text) for u in ("/upcoming", "/upcoming/years", f"/upcoming/years/{year}/export.csv")]
    r = c.post("/trips/archive-past", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    archived = c.get("/?archived=1").text
    assert "Ten days ago" in archived and "Thirty days ago" in archived and "Next month" not in archived
    assert "in the past" not in archived
    assert "in the past" not in c.get("/").text
    after = [_main(c.get(u).text) for u in ("/upcoming", "/upcoming/years", f"/upcoming/years/{year}/export.csv")]
    assert after == before


def test_a_post_with_no_csrf_token_changes_nothing(engine, monkeypatch):
    _seed(engine)
    c = _client(monkeypatch)
    assert c.post("/trips/archive-past", data={}, follow_redirects=False).status_code == 403
    assert "2 trips are in the past." in c.get("/").text
    assert "Archived trips" not in c.get("/").text
