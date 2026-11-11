"""The "hide stale" filter of the trip table (#277): a stale row is hidden, the badges count only the shown rows, and
the sort links keep the filter."""

import copy
import json
from datetime import datetime, timedelta, timezone

from tests.test_ingest_api import BODY
from tests.test_stale_flag import STALE, _row
from tests.test_trip_page import offer, trip  # noqa: F401 (fixture)


def _ingest_hours_ago(client, auth, trip_id, hours_ago, service_no, price):
    body = copy.deepcopy(BODY)
    captured = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    o = offer(price, service_no)
    if service_no == "ICE 123":  # an other departure: the newer capture does not mark ICE 105 as gone (#1386)
        o = json.loads(json.dumps(o).replace("2026-12-20T", "2026-12-21T"))  # the same times on the next day
    body.update(trip_id=trip_id, offers=[o], captured_at=captured.isoformat())
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _two_offers(client, auth, trip_id):
    # the old offer is the cheaper one, so the "cheapest" badge goes to it while it shows
    _ingest_hours_ago(client, auth, trip_id, 30, "ICE 105", "89.90")
    _ingest_hours_ago(client, auth, trip_id, 2, "ICE 123", "119.90")


def test_hide_stale_hides_the_stale_offer_only(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert "DB ICE 105" in page and "DB ICE 123" in page
    page = client.get(f"/trips/{trip_id}", params={"hide_stale": "true"}).text
    assert "DB ICE 105" not in page and "DB ICE 123" in page
    assert STALE not in page
    assert 'name="hide_stale" value="true" checked' in page


def test_the_badges_use_only_the_shown_rows(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    assert "cheapest" in _row(client.get(f"/trips/{trip_id}").text, "ICE 105")
    page = client.get(f"/trips/{trip_id}", params={"hide_stale": "true"}).text
    assert "cheapest" in _row(page, "ICE 123")


def test_a_sort_link_keeps_hide_stale(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two_offers(client, auth, trip_id)
    assert "hide_stale=" not in client.get(f"/trips/{trip_id}").text
    assert "hide_stale=True" in client.get(f"/trips/{trip_id}", params={"hide_stale": "true"}).text
