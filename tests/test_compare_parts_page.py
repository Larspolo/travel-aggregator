"""The compare view shows the parts of the effective cost side by side (#2087)."""

import copy
import re
from decimal import Decimal

from sqlalchemy import select

from app.models import Fare, Itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

PARAMS = {"hour_markup": "15"}  # 6 h = €90 time, 4 h = €60 time


def six_hours(price):
    """One leg, 6 hours, no transfer."""
    o = copy.deepcopy(direct(price))
    o["legs"] = [dict(o["legs"][0], arrive_at="2026-12-20T15:00:00+01:00")]
    return o


def _ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return {i.duration_min: i.id for i in its}


def _cells(page, label):
    """The opening tag and the inner HTML of each cell of one row of the compare table."""
    m = re.search(rf'<tr><th scope="row">{label}</th>(.*?)</tr>', page)
    assert m, f"no row {label}"
    return re.findall(r"<td([^>]*)>(.*?)</td>", m.group(1))


def test_price_and_time_rows_with_differences(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [six_hours("80.00"), direct("120.00")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare", params={**PARAMS, "it": [ids[360], ids[240]]}).text
    (_, price_a), (_, price_b) = _cells(page, "price")
    assert "€80" in price_a and "€120" in price_b and "+€40" in price_b and "+€" not in price_a
    (_, time_a), (_, time_b) = _cells(page, "time")
    assert "€90" in time_a and "€60" in time_b and "−€30" in time_b and "−" not in time_a
    assert 'scope="row">transfers</th>' not in page  # 0 transfers in both


def test_no_rate_column_shows_no_rate_and_the_other_is_best(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [six_hours("80.00"), direct("120.00")])
    ids = _ids(sessions, trip_id)
    with sessions() as s:
        for f in s.scalars(select(Fare).where(Fare.itinerary_id == ids[240])):
            f.currency, f.latest_price = "CZK", Decimal("120.00")
        s.commit()
    r = client.get(f"/trips/{trip_id}/compare", params={**PARAMS, "it": [ids[360], ids[240]]})
    assert r.status_code == 200
    (attr_a, price_a), (attr_b, price_b) = _cells(r.text, "price")
    assert "no rate" in price_b and "€80" in price_a
    assert "best" in attr_a and "best" not in attr_b
