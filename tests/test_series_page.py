"""The series page (#2500): each trip of a series with its date, best effective cost and search links."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fare, Itinerary, Leg, Trip, TripSeries
from app.ranking import format_total
from app.trip_import import import_trip
from app.web.pages import best_offer
from tests.test_trips_list import _client

T = datetime(2030, 12, 4, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def client(monkeypatch):
    return _client(monkeypatch)


def _series(engine) -> tuple[int, list[int]]:
    """The example of #2497: 4 trips every 2 weeks; only the first has an offer (EUR 97.40)."""
    with Session(engine) as s:
        series = TripSeries(step_weeks=2)
        s.add(series)
        s.flush()
        trips = [Trip(title="Amsterdam → Berlin", origin_text="Amsterdam", destination_text="Berlin",
                      date_from=date(2030, 12, 4) + timedelta(weeks=2 * k), series_id=series.id) for k in range(4)]
        s.add_all(trips)
        s.flush()
        it = Itinerary(trip=trips[0], fingerprint="s1", depart_at=T, arrive_at=T, duration_min=60)
        it.legs.append(Leg(seq=0, mode="train", from_name="Amsterdam", to_name="Berlin", depart_at=T, arrive_at=T,
                           depart_offset_min=0, arrive_offset_min=0))
        it.fares.append(Fare(source="bahn", latest_price=Decimal("97.40"), currency="EUR", latest_captured_at=T))
        s.add(it)
        s.add(Trip(title="Utrecht → Paris", origin_text="Utrecht", destination_text="Paris"))
        s.commit()
        return series.id, [t.id for t in trips]


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def test_four_lines_with_cost_links_and_search(engine, client):
    sid, ids = _series(engine)
    page = client.get(f"/series/{sid}").text
    assert page.count('class="series-trip"') == 4 and "Utrecht → Paris" not in page
    with Session(engine) as s:
        best = best_offer(s, s.get(Trip, ids[0]))
        expected = format_total(best[2])
    assert expected != "€97.40"  # the time part of the default profile (#2513)
    assert page.count(f"effective {expected}") == 1 and page.count("no offers yet") == 3
    assert page.index(f"effective {expected}") < page.index("no offers yet")
    for i in ids:
        assert f'href="/trips/{i}"' in page
    assert page.count("Open the search") == 4 and "2030-12-18" in page and "Berlin%20Hbf" in page


def test_unknown_series_is_404_and_login_needed(engine, client, monkeypatch):
    assert client.get("/series/999").status_code == 404
    from fastapi.testclient import TestClient

    from app.main import app
    sid, _ = _series(engine)
    assert "/series/" not in TestClient(app, follow_redirects=False).get(f"/series/{sid}").headers.get("location", "")


def test_trips_list_links_to_the_series(engine, client):
    sid, _ = _series(engine)
    assert f'href="/series/{sid}"' in client.get("/").text


def test_delete_leaves_the_others_and_one_trip_still_shows(engine, client):
    sid, ids = _series(engine)
    for i in ids[:3]:
        r = client.post(f"/trips/{i}/delete", data={"csrf_token": _csrf(client, f"/trips/{i}/delete")})
        assert r.status_code in (200, 303)
    page = client.get(f"/series/{sid}").text
    assert page.count('class="series-trip"') == 1 and f'href="/trips/{ids[3]}"' in page


def test_copy_of_a_series_trip_is_not_in_the_series(engine, client):
    sid, ids = _series(engine)
    client.post(f"/trips/{ids[0]}/copy", data={"csrf_token": _csrf(client, f"/trips/{ids[0]}/edit")})
    with Session(engine) as s:
        copy = s.scalars(select(Trip).where(Trip.title.like("%(copy)"))).one()
        assert copy.series_id is None
    assert client.get(f"/series/{sid}").text.count('class="series-trip"') == 4


def test_export_and_import_keep_no_series(engine, client):
    sid, ids = _series(engine)
    data = client.get(f"/trips/{ids[0]}/export.json").json()
    assert "series" not in str(list(data.get("trip", data).keys()))
    with Session(engine) as s:
        new_id = import_trip(s, data).trip_id
        s.commit()
        assert s.get(Trip, new_id).series_id is None
    assert client.get(f"/series/{sid}").text.count('class="series-trip"') == 4
