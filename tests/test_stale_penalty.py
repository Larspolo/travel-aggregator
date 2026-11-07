"""The stale penalty of a row (#276): a stale row costs `stale_penalty` more and its breakdown says "stale"."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost, format_breakdown
from app.risk import stale_extras
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
W = Weights(stale_penalty=Decimal("25"))
NOW = datetime(2026, 12, 20, 12, 0, tzinfo=UTC)
STALE_BEFORE = NOW - timedelta(hours=24)


def _fare(captured):
    return SimpleNamespace(latest_captured_at=captured)


def _it(*captured):
    return SimpleNamespace(fares=[_fare(c) for c in captured])


def _ingest_hours_ago(client, auth, trip_id, hours_ago, service_no, price):
    body = copy.deepcopy(BODY)
    captured = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    body.update(trip_id=trip_id, offers=[offer(price, service_no)], captured_at=captured.isoformat())
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _row(page, service_no):
    return next(part for part in page.split("<tr") if f"DB {service_no}" in part)


def test_a_stale_offer_adds_the_penalty_as_a_stale_part():
    it = _it(NOW - timedelta(hours=30))
    assert stale_extras(it, W, STALE_BEFORE) == (("stale", Decimal("25")),)
    base = effective_cost(Decimal("100"), 60, 0, W)
    with_penalty = effective_cost(Decimal("100"), 60, 0, W, stale_extras(it, W, STALE_BEFORE))
    assert with_penalty.total == base.total + 25
    assert "€25 stale" in format_breakdown(with_penalty)


def test_a_fresh_offer_or_a_zero_penalty_adds_no_part():
    assert stale_extras(_it(NOW - timedelta(hours=2)), W, STALE_BEFORE) == ()
    # the newest capture decides: one fresh capture makes the row fresh
    assert stale_extras(_it(NOW - timedelta(hours=30), NOW - timedelta(hours=2)), W, STALE_BEFORE) == ()
    assert stale_extras(_it(NOW - timedelta(hours=30)), Weights(), STALE_BEFORE) == ()


def test_the_trip_page_shows_the_stale_part_and_the_cheaper_stale_offer_ranks_below(trip):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_hours_ago(client, auth, trip_id, 30, "ICE 105", "100.00")  # stale: 100 + 25 = 125
    _ingest_hours_ago(client, auth, trip_id, 2, "ICE 123", "120.00")  # fresh: 120
    page = client.get(f"/trips/{trip_id}", params={"stale_penalty": "25"}).text
    assert "€25 stale" in _row(page, "ICE 105")
    assert "€25 stale" not in _row(page, "ICE 123")
    assert page.index("DB ICE 123") < page.index("DB ICE 105")


def test_the_default_penalty_changes_nothing(trip):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_hours_ago(client, auth, trip_id, 30, "ICE 105", "100.00")
    page = client.get(f"/trips/{trip_id}").text
    assert "€25 stale" not in page


def test_the_trip_page_accepts_the_stale_penalty_and_checks_its_range(trip):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_hours_ago(client, auth, trip_id, 2, "ICE 105", "100.00")  # the form shows only with a row
    assert 'name="stale_penalty"' in client.get(f"/trips/{trip_id}").text
    assert client.get(f"/trips/{trip_id}", params={"stale_penalty": "1001"}).status_code == 422
    assert client.get(f"/trips/{trip_id}", params={"stale_penalty": "-1"}).status_code == 422
