"""A break-even value links to the compare view re-ranked with that hour value (#896, epic #892)."""

import html
import re
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from app.models import Itinerary
from tests.test_compare_tradeoff import _breakeven_cells, timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _break_even_hrefs(page):
    row = re.search(r'<th scope="row">Break-even.*?</tr>', page, re.S).group(0)
    return re.findall(r'<a href="([^"]+)"', row)


def test_the_break_even_value_links_to_the_page_with_that_hour_value(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # at 10 €/h: 100 + 5 × 10 = 150 (best now) and 125 + 3 × 10 = 155; equal at 12.50 €/h, rounded up to 13
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id)).all()
        ids = {i.duration_min: i.id for i in its}
    params = {"hour_markup": "10", "transfer_markup": "2", "it": [ids[300], ids[180]]}
    page = client.get(f"/trips/{trip_id}/compare", params=params).text
    assert _breakeven_cells(page) == ["Best now", "Better above €12.50/h"]

    (href,) = _break_even_hrefs(page)
    query = parse_qs(urlsplit(html.unescape(href)).query)
    assert urlsplit(html.unescape(href)).path == f"/trips/{trip_id}/compare"
    assert query["hour_markup"] == ["13"]  # the value rounded up: the other offer is better above it
    assert query["transfer_markup"] == ["2"]  # the other weights stay
    assert query["it"] == [str(ids[300]), str(ids[180])]

    # the page of the link ranks the faster itinerary first: "Best now" in its column (the second one)
    linked = client.get(html.unescape(href)).text
    assert _breakeven_cells(linked) == ["Better below €12.50/h", "Best now"]
