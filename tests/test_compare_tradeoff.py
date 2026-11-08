"""The break-even hour value on the compare view (#894, epic #892)."""

import copy
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary
from app.web.pages import row_cost
from app.ranking import Weights
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def timed(price, hours, service):
    """One leg from 09:00 that lasts `hours` hours, no transfer."""
    o = copy.deepcopy(offer(price, service))
    o["legs"] = [dict(o["legs"][0], to_name="Zürich HB", depart_at="2026-12-20T09:00:00+01:00",
                      arrive_at=f"2026-12-20T{9 + hours:02d}:00:00+01:00")]
    return o


def _ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return {i.duration_min: i.id for i in its}


def _breakeven_cells(page):
    row = re.search(r'<th scope="row">Break-even.*?</tr>', page, re.S).group(0)
    return re.findall(r"<td>([^<]*)</td>", row)


def test_the_best_column_and_the_break_even_of_the_other(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # at 10 €/h: 100 + 5 × 10 = 150 (best) and 125 + 3 × 10 = 155; equal at 12.50 €/h
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare", params={"hour_markup": "10", "it": [ids[300], ids[180]]}).text
    assert _breakeven_cells(page) == ["Best now", "Better above €12.50/h"]
    assert "(yours: €10/h)" in page


def test_the_same_duration_has_no_break_even(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 4, "ICE 1"), timed("120.00", 4, "ICE 2")])
    with sessions() as s:
        ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)
                                       .order_by(Itinerary.id)).all()]
    page = client.get(f"/trips/{trip_id}/compare", params={"hour_markup": "10", "it": ids}).text
    assert _breakeven_cells(page) == ["Best now", "—"]


def test_both_costs_are_equal_at_the_shown_hour_value(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 5, "ICE 1"), timed("125.00", 3, "ICE 2")])
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        by_dur = {i.duration_min: i for i in its}
        a, b = by_dur[300], by_dur[180]
        weights = Weights(hour_markup=Decimal("12.5"))
        stale_before = datetime.now(timezone.utc) - timedelta(hours=weights.stale_hours)
        ca = row_cost(a, a.fares, [], weights, stale_before, {})[1].total
        cb = row_cost(b, b.fares, [], weights, stale_before, {})[1].total
    # the durations differ by 2 hours: at most 1 cent per hour of difference
    assert abs(ca - cb) <= Decimal("0.02")
