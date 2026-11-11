"""The checked bag of a trip on each page of `row_cost()` (#2398): best offer, compare, share, rail pass."""

from decimal import Decimal

from sqlalchemy import select

from app.auth import require_login
from app.main import app
from app.models import Itinerary, RailPass, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from app.web.pages import best_for_weights, row_cost
from tests.test_ingest_best import setup  # noqa: F401 (fixture)
from tests.test_leave_after_pages import _client, _share_page  # noqa: F401
from tests.test_trip_ranking_page import direct

D = Decimal
FEE = {"hour_markup": D("0"), "transfer_markup": D("0"), "baggage_fee": D("40")}
FLIGHT = dict(direct("50.00")["legs"][0], mode="flight", service_no="KL 1")


def _flight_trip(setup, sessions, checked_bag):  # noqa: F811
    setup([dict(direct("50.00"), legs=[FLIGHT]), dict(direct("60.00"), legs=[dict(FLIGHT, service_no="KL 2")])])
    with sessions() as s:
        trip = s.query(Trip).one()
        trip.checked_bag = checked_bag
        s.commit()
        return trip.id


def _set_bag(sessions, trip_id, checked_bag):
    with sessions() as s:
        s.get(Trip, trip_id).checked_bag = checked_bag
        s.commit()


def test_the_best_offer_has_no_bag_cost_on_a_none_trip(setup, sessions):  # noqa: F811
    totals = {}
    trip_id = _flight_trip(setup, sessions, None)
    for bag in (None, "none"):
        _set_bag(sessions, trip_id, bag)
        with sessions() as s:
            totals[bag] = best_for_weights(s, s.get(Trip, trip_id), Weights(**FEE))[2].total
    assert totals[None] - totals["none"] == D("40")


def test_the_compare_page_shows_no_checked_bag_on_a_none_trip(setup, sessions):  # noqa: F811
    client = _client()
    try:
        trip_id = _flight_trip(setup, sessions, None)
        for bag, text in ((None, "€40 baggage (estimate)"), ("none", "€0 no checked bag (trip)")):
            _set_bag(sessions, trip_id, bag)
            with sessions() as s:
                ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))]
            page = client.get(f"/trips/{trip_id}/compare", params={"it": ids, "hour_markup": 0,
                                                                    "transfer_markup": 0, "baggage_fee": 40}).text
            assert text in page
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_the_share_page_shows_no_checked_bag_on_a_none_trip(setup, sessions):  # noqa: F811
    trip_id = _flight_trip(setup, sessions, "none")
    with sessions() as s:
        p = ScoreProfile(name="Bag", is_default=False, config_json=to_config(Weights(**FEE)))
        s.add(p)
        s.flush()
        s.get(Trip, trip_id).profile_id = p.id
        s.commit()
    client = _client()
    try:
        page = _share_page(client, trip_id)
        assert "no checked bag (trip)" in page and "baggage (estimate)" not in page
    finally:
        app.dependency_overrides.pop(require_login, None)


def test_the_rail_pass_branch_has_no_bag_cost_on_a_none_trip(setup, sessions):  # noqa: F811
    from datetime import date, datetime, timezone
    trip_id = _flight_trip(setup, sessions, "none")
    with sessions() as s:
        rp = RailPass(name="Interrail", first_day=date(2026, 12, 1), last_day=date(2026, 12, 31),
                      day_cost=D("40.00"), carriers="", updated_at=datetime.now(timezone.utc))
        s.add(rp)
        s.flush()
        s.get(Trip, trip_id).rail_pass_id = rp.id
        s.commit()
    with sessions() as s:
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).first()
        fare, b = row_cost(it, it.fares, [], Weights(**FEE), datetime(2000, 1, 1, tzinfo=timezone.utc))
    labels = [label for label, _ in b.extras]
    assert "no checked bag (trip)" in labels and not any(label.startswith("baggage") for label in labels)
