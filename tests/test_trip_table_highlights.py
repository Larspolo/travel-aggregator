"""The cheapest, fastest and best-value rows of the trip table show a badge, after the filters (#113)."""

import re

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct
from tests.test_trip_table_sort_filter import bus


def badges(page):
    """The badges of each row, in the order of the rows."""
    rows = [re.findall(r'<span class="badge">([^<]+)</span>', row) for row in page.split("<tr")[2:]]
    return [r for r in rows if r]


def test_each_badge_marks_its_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    # 89.90 + 118 time + 10 = 217.90 (the cheapest); the direct one 150 + 60 = 210 (best value, fastest)
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    rows = badges(client.get(f"/trips/{trip_id}").text)
    assert rows == [["best value", "fastest"], ["cheapest"]]


def test_the_badges_use_the_rows_after_the_filters(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00"), bus("20.00")])
    assert ["best value", "cheapest", "fastest"] in badges(client.get(f"/trips/{trip_id}").text)
    rows = badges(client.get(f"/trips/{trip_id}?mode=train").text)
    assert sorted(b for r in rows for b in r) == ["best value", "cheapest", "fastest"] and ["cheapest"] in rows
