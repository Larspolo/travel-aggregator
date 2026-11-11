"""The ingest response names the itinerary of the best offer (#2365)."""

from sqlalchemy import func, select

from app.models import Itinerary
from tests.test_ingest_best import offer, other_legs, setup  # noqa: F401  (pytest fixture)


def newest_itinerary_id(sessions):
    with sessions() as s:
        return s.scalar(select(func.max(Itinerary.id)))


def test_best_carries_the_itinerary_id_of_the_best_offer(setup, sessions):  # noqa: F811  (the fixture)
    first = setup([offer("120.00")])["best"]
    assert first["itinerary_id"] == newest_itinerary_id(sessions)
    cheaper = setup([offer("80.00", other_legs(9))])["best"]
    assert cheaper["itinerary_id"] == newest_itinerary_id(sessions)
    assert cheaper["itinerary_id"] != first["itinerary_id"]
    worse = setup([offer("300.00", other_legs(11))])["best"]
    assert worse["itinerary_id"] == cheaper["itinerary_id"]
