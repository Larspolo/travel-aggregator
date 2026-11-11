"""The hour value of a trip on each page that ranks its offers (#2424): the best offer, compare, share, the
trade-off line and the kept paid fare give the same cost as the trip page."""

import re
from decimal import Decimal

from sqlalchemy import select

from app.auth import require_login
from app.main import app
from app.models import Itinerary, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from app.web.pages import best_offer, keep_paid_fare
from tests.test_ingest_best import setup  # noqa: F401 (fixture)
from tests.test_leave_after_pages import _client, _share_page  # noqa: F401
from tests.test_trip_ranking_page import direct

D = Decimal
FAST = direct("50.00")  # 4 h
SLOW = dict(direct("30.00"), legs=[dict(FAST["legs"][0], service_no="ICE 8", arrive_at="2026-12-20T15:00:00+01:00")])


def _trip(setup, sessions, hour_value):  # noqa: F811
    """A trip with the 4 h train and a 6 h train, a profile of €15/h and the trip hour value `hour_value`."""
    setup([FAST, SLOW])
    with sessions() as s:
        p = ScoreProfile(name="Fifteen", is_default=False,
                         config_json=to_config(Weights(hour_markup=D("15"), transfer_markup=D("0"))))
        s.add(p)
        s.flush()
        trip = s.query(Trip).one()
        trip.profile_id, trip.hour_value = p.id, hour_value
        s.commit()
        return trip.id


def _set_hours(sessions, trip_id, hour_value):
    with sessions() as s:
        s.get(Trip, trip_id).hour_value = hour_value
        s.commit()


def _totals(page):
    texts = re.findall(r'class="breakdown[^"]*">([^<]*)<', page)
    return [D(re.findall(r"= €([\d.]+)", t)[-1]) for t in texts]


def test_the_best_offer_uses_the_trip_value_and_else_the_profile(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, None)
    with sessions() as s:
        profile = best_offer(s, s.get(Trip, trip_id))[2].total
    _set_hours(sessions, trip_id, D("30"))
    with sessions() as s:
        _, fare, cost = best_offer(s, s.get(Trip, trip_id))
    assert fare.latest_price == D("50.00") and cost.total - profile == D("60.00")  # 4 h × (30 − 15)


def test_compare_and_share_give_the_cost_of_the_trip_page(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, D("30"))
    client = _client()
    try:
        trip_page = client.get(f"/trips/{trip_id}").text
        best = min(_totals(trip_page))
        assert best == D("170.00")  # 50 + 4 h × 30
        with sessions() as s:
            ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id))]
        assert min(_totals(client.get(f"/trips/{trip_id}/compare", params={"it": ids}).text)) == best
        assert min(_totals(_share_page(client, trip_id))) == best
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_the_trade_off_line_says_the_trip_value(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, D("30"))
    client = _client()
    try:
        assert "(yours: €30/h)" in client.get(f"/trips/{trip_id}").text
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_the_kept_paid_fare_is_the_main_fare_at_the_trip_value(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, D("30"))
    with sessions() as s:
        _, fare, _ = best_offer(s, s.get(Trip, trip_id))
        it = s.get(Itinerary, fare.itinerary_id)
        keep_paid_fare(s, it)
        assert (it.booked_fare_id, it.booked_price) == (fare.id, D("50.00"))
