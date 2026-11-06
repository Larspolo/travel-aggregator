"""The short-transfer penalty of an itinerary (#173)."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import transfer_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
W = Weights(short_transfer_min=10, short_transfer_penalty=Decimal("20"))
T0 = datetime(2026, 12, 20, 12, 0, tzinfo=UTC)


def _it(*gaps_min):
    """Give an itinerary of legs: each leg is 30 minutes long; the gaps between the legs are given in minutes."""
    legs, t = [], T0
    legs.append(SimpleNamespace(depart_at=t, arrive_at=t + timedelta(minutes=30)))
    for gap in gaps_min:
        dep = legs[-1].arrive_at + timedelta(minutes=gap)
        legs.append(SimpleNamespace(depart_at=dep, arrive_at=dep + timedelta(minutes=30)))
    return SimpleNamespace(legs=legs)


def test_a_short_transfer_adds_the_penalty():
    assert transfer_extras(_it(6), W) == (("short transfer", Decimal("20")),)


def test_a_long_transfer_one_leg_and_a_zero_penalty_add_no_part():
    assert transfer_extras(_it(15), W) == ()
    assert transfer_extras(_it(), W) == ()
    assert transfer_extras(_it(6), Weights(short_transfer_min=10)) == ()


def test_the_minimum_is_strict():
    assert transfer_extras(_it(10), W) == ()
    assert transfer_extras(_it(9), W) == (("short transfer", Decimal("20")),)


def test_several_short_transfers_give_one_part_with_the_sum():
    assert transfer_extras(_it(6, 3, 30), W) == (("short transfer", Decimal("40")),)


def test_the_trip_page_accepts_and_shows_the_penalty(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("89.90"))  # the transfer is 31 minutes
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert 'name="short_transfer_min"' in page and 'name="short_transfer_penalty"' in page and "short transfer" not in page
    page = client.get(f"/trips/{trip_id}?short_transfer_min=40&short_transfer_penalty=20").text
    assert "€20 short transfer" in page
    assert client.get(f"/trips/{trip_id}?short_transfer_min=241").status_code == 422
    assert client.get(f"/trips/{trip_id}?short_transfer_penalty=-1").status_code == 422
