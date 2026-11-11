"""The best offer of the panel and the journey skip the departed offers (#1392, epic #1390).
A booked departed offer stays the chosen offer of its direction."""
from datetime import datetime, timezone

import pytest

from app.models import Itinerary, Trip
from app.ranking import Weights
from app.web.pages import _chosen_offer, best_for_weights
from tests.test_trip_hide import itinerary_at
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

BEFORE = datetime(2026, 12, 1, 6, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def two(trip, sessions):  # noqa: F811
    """Two offers: the cheap one departs at 07:34 UTC on 1 Dec 2026, the dear one at 12:00 UTC."""
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90", "ICE 1"), offer("119.90", "ICE 2")])
    early, late = itinerary_at(sessions, tid, "89.90"), itinerary_at(sessions, tid, "119.90")
    with sessions() as s:
        s.get(Itinerary, early).depart_at = datetime(2026, 12, 1, 7, 34, tzinfo=timezone.utc)
        s.get(Itinerary, late).depart_at = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
        s.commit()
    return tid, early, late, sessions


def test_best_for_weights_gives_the_cheap_offer_before_it_departs(two):
    tid, early, late, sessions = two
    with sessions() as s:
        best = best_for_weights(s, s.get(Trip, tid), Weights(), BEFORE)
    assert best[0].id == early


def test_best_for_weights_gives_the_next_offer_after_the_cheap_one_departs(two):
    tid, early, late, sessions = two
    with sessions() as s:
        best = best_for_weights(s, s.get(Trip, tid), Weights(), AFTER)
    assert best[0].id == late


def test_best_for_weights_keeps_a_booked_departed_offer(two):
    tid, early, late, sessions = two
    with sessions() as s:
        s.get(Itinerary, early).booked = True
        s.commit()
        best = best_for_weights(s, s.get(Trip, tid), Weights(), AFTER)
    assert best[0].id == early


def test_chosen_offer_gives_the_next_offer_after_the_cheap_one_departs(two):
    tid, early, late, sessions = two
    with sessions() as s:
        chosen = _chosen_offer(s, s.get(Trip, tid), Weights(), [], AFTER)
    assert chosen[0].id == late


def test_chosen_offer_keeps_a_booked_departed_offer(two):
    tid, early, late, sessions = two
    with sessions() as s:
        s.get(Itinerary, early).booked = True
        s.commit()
        chosen = _chosen_offer(s, s.get(Trip, tid), Weights(), [], AFTER)
    assert chosen[0].id == early
