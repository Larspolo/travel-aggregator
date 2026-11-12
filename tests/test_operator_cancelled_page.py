"""An offer that the operator cancelled shows the mark, sorts last and is never the best offer (#2630)."""
from datetime import datetime, timezone

import pytest

from app.models import Itinerary, Trip
from app.ranking import Weights
from app.web.pages import best_for_weights
from tests.test_trip_hide import itinerary_at
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_upcoming_page import SOON, add, client  # noqa: F401  (client is a fixture)

MARK = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def two(trip, sessions):  # noqa: F811
    tclient, auth, tid = trip
    ingest(tclient, auth, tid, [offer("89.90", "ICE 1"), offer("119.90", "ICE 2")])
    cheap, dear = itinerary_at(sessions, tid, "89.90"), itinerary_at(sessions, tid, "119.90")
    return tclient, tid, cheap, dear, sessions


def test_a_cancelled_cheap_row_is_second_and_not_the_best(two):
    tclient, tid, cheap, dear, sessions = two
    assert 'badge cancelled' not in tclient.get(f"/trips/{tid}").text
    with sessions() as s:
        s.get(Itinerary, cheap).operator_cancelled_at = MARK
        s.commit()
    page = tclient.get(f"/trips/{tid}").text
    assert page.index(f'id="it-{dear}"') < page.index(f'id="it-{cheap}"')
    row = page[page.index(f'id="it-{cheap}"'):]
    row = row[:row.index("</tr>")]
    assert "cancelled by the operator</span>" in row and 'class="badge cancelled"' in row
    with sessions() as s:
        best = best_for_weights(s, s.get(Trip, tid), Weights())
        assert best[0].id == dear


def test_a_booked_cancelled_journey_shows_the_warning(client, sessions):  # noqa: F811
    with sessions() as s:
        _, it_id = add(s, "Cancelled trip", SOON)
    assert "Cancelled by the operator" not in client.get("/upcoming").text
    with sessions() as s:
        s.get(Itinerary, it_id).operator_cancelled_at = MARK
        s.commit()
    assert "Cancelled by the operator: check the booking" in client.get("/upcoming").text
