"""The trip page hides the departed offers; "show departed" shows them greyed and last (#1391)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import app.departed
from app.departed import not_departed
from app.models import Itinerary
from tests.test_trip_hide import itinerary_at
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def two(trip, sessions, monkeypatch):  # noqa: F811
    """Two offers: the cheap one departs at 07:34 UTC on the day of NOW, the dear one later."""
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90", "ICE 1"), offer("119.90", "ICE 2")])
    early, late = itinerary_at(sessions, tid, "89.90"), itinerary_at(sessions, tid, "119.90")
    with sessions() as s:
        s.get(Itinerary, early).depart_at = datetime(2026, 12, 1, 7, 34, tzinfo=timezone.utc)
        s.get(Itinerary, late).depart_at = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
        s.commit()
    monkeypatch.setattr(app.departed, "clock", lambda: NOW)
    return client, tid, early, sessions


def test_the_clause_keeps_a_booked_departed_offer(two):
    client, tid, early, sessions = two
    with sessions() as s:
        assert set(s.scalars(select(Itinerary.id).where(Itinerary.trip_id == tid, not_departed(NOW)))) == {
            itinerary_at(sessions, tid, "119.90")}
        s.get(Itinerary, early).booked = True
        s.commit()
        assert early in set(s.scalars(select(Itinerary.id).where(Itinerary.trip_id == tid, not_departed(NOW))))


def test_a_departed_offer_is_not_in_the_table(two):
    client, tid, early, sessions = two
    page = client.get(f"/trips/{tid}").text
    assert f'id="it-{early}"' not in page and "€119.90" in page
    with sessions() as s:
        s.get(Itinerary, early).booked = True
        s.commit()
    assert f'id="it-{early}"' in client.get(f"/trips/{tid}").text


def test_show_departed_shows_the_row_greyed_last_with_no_badge(two):
    client, tid, early, sessions = two
    page = client.get(f"/trips/{tid}?show_departed=true").text
    late = itinerary_at(sessions, tid, "119.90")
    assert page.index(f'id="it-{late}"') < page.index(f'id="it-{early}"')
    row = page[page.index(f'id="it-{early}"'):]
    row = row[:row.index("</tr>")]
    assert 'class="departed muted"' in row and "departed</span>" in row
    assert "cheapest" not in row and "best value" not in row
    assert 'name="show_departed" value="true" checked' in page
