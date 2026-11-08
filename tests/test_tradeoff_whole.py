"""The whole break-even feature of epic #892 (#912): a train with a night leg and access time, a day bus with egress
time and a flight with airport time. Each shown break-even value makes the two effective costs equal."""

import copy
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import AccessTime, Itinerary
from app.ranking import Weights
from app.web.pages import row_cost
from tests.test_compare_tradeoff import _breakeven_cells
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_tradeoff import _lines

Y = datetime.now(timezone.utc).year + 1
H, N = "20", "5"
VALUE = re.compile(r"[Bb]etter (?:above|below) €([0-9.]+)/h")


def _one(price, service, mode, start, depart, arrive, end):
    o = copy.deepcopy(offer(price, service))
    o["legs"] = [dict(o["legs"][0], mode=mode, from_name=start, to_name=end, depart_at=depart, arrive_at=arrive)]
    return o


def _fixture(client, auth, trip_id, sessions):
    ingest(client, auth, trip_id, [
        _one("60.00", "NJ 40", "train", "Amsterdam Centraal", f"{Y}-03-10T22:00:00+01:00",
             f"{Y}-03-11T07:00:00+01:00", "Zürich HB"),
        _one("30.00", "FLX 1", "bus", "Amsterdam Sloterdijk", f"{Y}-03-10T08:00:00+01:00",
             f"{Y}-03-10T18:00:00+01:00", "Zürich Carparkplatz"),
        _one("150.00", "KL 1953", "flight", "Amsterdam Schiphol", f"{Y}-03-10T10:00:00+01:00",
             f"{Y}-03-10T11:30:00+01:00", "Zürich Flughafen")])
    with sessions() as s:
        s.add_all([AccessTime(place_text="Amsterdam Centraal", kind="access", minutes=30, cost=Decimal("3")),
                   AccessTime(place_text="Zürich Carparkplatz", kind="egress", minutes=20, cost=Decimal("2"))])
        s.commit()
        return {i.legs[0].service_no: i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}


def _check(sessions, values, ids):
    """Each (row id, X): the row and the best offer of all rows have the same cost at hour value X."""
    with sessions() as s:
        places = s.scalars(select(AccessTime)).all()
        its = {i: s.get(Itinerary, i) for i in ids}
        stale = datetime.now(timezone.utc) - timedelta(hours=Weights().stale_hours)
        now = Weights(hour_markup=Decimal(H), night_hour_markup=Decimal(N))
        best = min(its.values(), key=lambda it: row_cost(it, it.fares, places, now, stale, {})[1].total)
        def diff(row_id, x):
            w = Weights(hour_markup=x, night_hour_markup=Decimal(N))
            a, b = (row_cost(it, it.fares, places, w, stale, {})[1].total for it in (its[row_id], best))
            return a - b
        for row_id, x in values:
            x = Decimal(x)
            hours = abs(Decimal(its[row_id].duration_min - best.duration_min)) / 60
            # the shown value is rounded to cents: the costs are equal there, or they cross within one cent of it
            # (the night part changes the slope, so 1 cent of hour value can be more than 1 cent per hour of duration)
            cent = Decimal("0.01")
            assert (abs(diff(row_id, x)) <= cent * max(1, hours)
                    or diff(row_id, x - cent) * diff(row_id, x + cent) <= 0), (row_id, x)


def test_the_compare_view_values_make_both_costs_equal(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids = list(_fixture(client, auth, trip_id, sessions).values())
    page = client.get(f"/trips/{trip_id}/compare", params={"it": ids, "hour_markup": H, "night_hour_markup": N}).text
    values = [(i, m.group(1)) for i, cell in zip(ids, _breakeven_cells(page)) if (m := VALUE.search(cell))]
    assert values
    _check(sessions, values, ids)


def test_the_trip_page_values_make_both_costs_equal(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids = list(_fixture(client, auth, trip_id, sessions).values())
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": H, "night_hour_markup": N}).text
    values = [(i, VALUE.search(text).group(1)) for i, text in _lines(page).items()]
    assert values
    _check(sessions, values, ids)
