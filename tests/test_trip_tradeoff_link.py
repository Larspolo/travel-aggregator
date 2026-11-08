"""The break-even value in the expanded row of the trip table links to the trip page re-ranked (#920, epic #892)."""

import html
import re
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from app.models import Itinerary
from tests.test_compare_tradeoff import timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_tradeoff import _lines


def _link(page):
    """The href of the link in the break-even line of the trip table, or None when the line has no link."""
    line = re.search(r'<p class="tradeoff muted">.*?</p>', page, re.S)
    if line is None:
        return None
    hrefs = re.findall(r'<a href="([^"]+)"', line.group(0))
    assert len(hrefs) <= 1
    return html.unescape(hrefs[0]) if hrefs else None


def test_the_break_even_value_links_to_the_trip_page_with_that_hour_value(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # at 10 €/h: 100 + 5 × 10 = 150 (best now) and 125 + 3 × 10 = 155; equal at 12.50 €/h, rounded up to 13
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    with sessions() as s:
        ids = {i.duration_min: i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}
    params = {"hour_markup": "10", "transfer_markup": "2", "sort": "price"}
    page = client.get(f"/trips/{trip_id}", params=params).text
    href = _link(page)
    assert href is not None
    assert urlsplit(href).path == f"/trips/{trip_id}"
    query = parse_qs(urlsplit(href).query)
    assert query["hour_markup"] == ["13"]  # the value rounded up: the other row is better above it
    assert query["transfer_markup"] == ["2"]  # the other weights stay
    assert query["sort"] == ["price"]  # the sort of the page stays

    # the page of the link ranks the faster itinerary first: the break-even line moves to the slower row
    linked = client.get(href).text
    lines = _lines(linked)
    assert set(lines) == {ids[300]}
    assert "better below €12.50/h" in lines[ids[300]]
    assert ids[180] not in lines


def test_a_break_even_value_above_100_per_hour_has_no_link(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # the faster offer costs 900 € more: its break-even is 450 €/h, above the range of hour_markup
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("1000.00", 3, "ICE 2")])
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "10", "sort": "price"}).text
    assert "better above €450/h" in _lines(page).popitem()[1]
    assert _link(page) is None
