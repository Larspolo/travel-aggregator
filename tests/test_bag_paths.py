"""The bags of the fare in the best offer of a trip and in the compare view (#1551, epic #1524)."""

from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary, Leg, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from app.web.pages import best_offer
from tests.test_bag_score import _flight
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _ids(sessions, trip_id):
    """The itinerary id of each flight number of the trip."""
    with sessions() as s:
        rows = s.execute(select(Leg.service_no, Itinerary.id).join(Itinerary, Leg.itinerary_id == Itinerary.id)
                         .where(Itinerary.trip_id == trip_id)).all()
        return dict(rows)


def _set_default_fee(sessions, fee):
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.add(ScoreProfile(name="Bags", is_default=True, config_json=to_config(Weights(baggage_fee=Decimal(fee)))))
        s.commit()


def test_the_compare_view_has_the_bag_part_of_each_fare(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_flight("100.00", "KL 1", checked_bags_included=1),
                                   _flight("100.00", "KL 2", checked_bag_price="25.06"),
                                   _flight("100.00", "KL 3")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare",
                      params={"baggage_fee": "30", "it": [ids["KL 1"], ids["KL 2"], ids["KL 3"]]}).text
    assert "€0 baggage (included)" in page
    assert "€25.06 baggage" in page
    assert "€30 baggage" in page


def test_the_best_offer_of_the_list_takes_the_included_bag(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    # KL 1 is EUR 1 cheaper, but without a bag it costs EUR 30 more than KL 2 with an included bag at a fee of 30
    ingest(client, auth, trip_id, [_flight("99.00", "KL 1"), _flight("100.00", "KL 2", checked_bags_included=1)])
    _set_default_fee(sessions, "30")
    with sessions() as s:
        it, _, _ = best_offer(s, s.get(Trip, trip_id))
        assert it.legs[0].service_no == "KL 2"


def test_a_bag_fee_of_zero_does_not_change_the_best_offer(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_flight("99.00", "KL 1"), _flight("100.00", "KL 2", checked_bags_included=1)])
    _set_default_fee(sessions, "0")
    with sessions() as s:
        it, _, _ = best_offer(s, s.get(Trip, trip_id))
        assert it.legs[0].service_no == "KL 1"
