"""The stale flag, the stale penalty and the stale filter work together on the trip page (#278, epic #274)."""

import copy
from datetime import datetime, timedelta, timezone

from tests.test_ingest_api import BODY
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_table_highlights import badges

STALE = "stale, price may have changed"


def _ingest_hours_ago(client, auth, trip_id, hours_ago, service_no, price):
    body = copy.deepcopy(BODY)
    captured = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    body.update(trip_id=trip_id, offers=[offer(price, service_no)], captured_at=captured.isoformat())
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _row(page, service_no):
    return next(part for part in page.split("<tr") if f"DB {service_no}" in part)


def _setup(client, auth, trip_id):
    _ingest_hours_ago(client, auth, trip_id, 1, "ICE 123", "120.00")  # fresh
    _ingest_hours_ago(client, auth, trip_id, 30, "ICE 105", "100.00")  # stale


def test_with_no_parameter_the_stale_offer_is_flagged_and_ranks_first(trip):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert STALE in _row(page, "ICE 105") and STALE not in _row(page, "ICE 123")
    assert page.index("ICE 105") < page.index("ICE 123")  # no penalty by default: 100 < 120


def test_a_stale_penalty_shows_the_stale_part_and_ranks_the_fresh_offer_first(trip):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}", params={"stale_penalty": "50"}).text
    assert "€50 stale" in _row(page, "ICE 105")  # the breakdown of the stale offer
    assert page.index("ICE 123") < page.index("ICE 105")  # 120 < 100 + 50


def test_hide_stale_shows_only_the_fresh_offer_with_the_cheapest_badge(trip):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}", params={"hide_stale": "1"}).text
    assert "ICE 123" in page and "ICE 105" not in page
    rows = badges(page)
    assert len(rows) == 1 and "cheapest" in rows[0]
