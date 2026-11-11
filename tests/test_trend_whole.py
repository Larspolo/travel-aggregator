"""The whole price trend of a trip (#849): two fares on three days through the ingest API give three chart points
with the lowest EUR value of each day; a trip with captures on one day only shows no chart."""

import copy
import re

from tests.test_history_whole import capture, trip  # noqa: F401  (trip is a fixture)
from tests.test_ingest_api import BODY


def capture_fare(client, auth, trip_id, price, captured_at, fare_name):
    """Like `capture()` of tests/test_history_whole.py, for the second fare of the same itinerary."""
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, captured_at=captured_at)
    offer = copy.deepcopy(BODY["offers"][0])
    offer.update(price_amount=price, fare_name=fare_name)
    body["offers"] = [offer]
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def test_two_fares_on_three_days_give_three_points_with_the_lowest_day_value(trip):  # noqa: F811
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "90.00", "2026-11-03T10:00:00Z")  # fare A
    capture_fare(client, auth, trip_id, "85.00", "2026-11-04T10:00:00Z", "Flexpreis")  # fare B
    capture(client, auth, trip_id, "99.00", "2026-11-05T10:00:00Z")  # fare A
    capture_fare(client, auth, trip_id, "99.00", "2026-11-05T10:00:00Z", "Flexpreis")  # fare B
    page = client.get(f"/trips/{trip_id}").text
    assert "<h2>Price trend</h2>" in page
    section = re.search(r'<section class="trend card".*?</section>', page, re.S)
    assert section is not None
    assert section.group(0).count("<circle") == 3
    for title in ("2026-11-03: €90.00", "2026-11-04: €85.00", "2026-11-05: €99.00"):
        assert f"<title>{title}</title>" in section.group(0)
    assert "low €85.00" in page and "high €" in page  # high of both lines (#2141)


def test_a_trip_with_captures_on_one_day_only_shows_no_chart(trip):  # noqa: F811
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "90.00", "2026-11-03T10:00:00Z")  # fare A
    capture_fare(client, auth, trip_id, "85.00", "2026-11-03T10:00:00Z", "Flexpreis")  # fare B
    assert "Price trend" not in client.get(f"/trips/{trip_id}").text
