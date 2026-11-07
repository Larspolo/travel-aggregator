"""The stale flag of a trip row (#275): a row whose newest capture is older than `stale_hours` says so."""

import copy
from datetime import datetime, timedelta, timezone

from tests.test_ingest_api import BODY
from tests.test_trip_page import ingest, offer, trip  # noqa: F401 (fixture)

STALE = "stale, price may have changed"


def _ingest_hours_ago(client, auth, trip_id, hours_ago, service_no):
    body = copy.deepcopy(BODY)
    captured = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    body.update(trip_id=trip_id, offers=[offer("89.90", service_no)], captured_at=captured.isoformat())
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _row(page, service_no):
    return next(part for part in page.split("<tr") if f"DB {service_no}" in part)


def test_an_old_offer_is_flagged_and_a_new_one_is_not(trip):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_hours_ago(client, auth, trip_id, 30, "ICE 105")
    _ingest_hours_ago(client, auth, trip_id, 2, "ICE 123")
    page = client.get(f"/trips/{trip_id}").text
    assert STALE in _row(page, "ICE 105")
    assert STALE not in _row(page, "ICE 123")


def test_a_longer_stale_hours_removes_the_flag(trip):  # noqa: F811
    client, auth, trip_id = trip
    _ingest_hours_ago(client, auth, trip_id, 30, "ICE 105")
    assert STALE in client.get(f"/trips/{trip_id}").text
    page = client.get(f"/trips/{trip_id}", params={"stale_hours": 48}).text
    assert STALE not in _row(page, "ICE 105")


def test_the_stale_hours_range_is_checked(trip):  # noqa: F811
    client, _auth, trip_id = trip
    for value in (0, 721):
        assert client.get(f"/trips/{trip_id}", params={"stale_hours": value}).status_code == 422
