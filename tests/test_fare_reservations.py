"""The mandatory seat reservations of a fare at ingest (#1620): the `reservation` of each leg, the count on the fare."""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select

from app.models import Fare
from app.schemas import OfferIn
from tests.test_self_transfer import post
from tests.test_trip_booked import _alembic
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)


def reserved(*status, price="89.90", fare="Sparpreis"):
    o = offer(price, fare=fare)
    legs = o["legs"]
    legs.append(dict(legs[1], from_name="Zürich HB", to_name="Chur", depart_at="2026-12-20T15:37:00+01:00",
                     arrive_at="2026-12-20T16:52:00+01:00"))
    for leg, s in zip(legs, status):
        if s is not None:
            leg["reservation"] = s
    return o


def counts(sessions):
    with sessions() as s:
        return sorted(s.execute(select(Fare.fare_name, Fare.reservation_legs)).all())


@pytest.mark.parametrize("status, count", [
    ((None, None, None), 0), (("required", "included", None), 1), (("required", "required", "included"), 2),
    (("included", "included", "included"), 0),
])
def test_count_of_reservation_legs(status, count):
    assert OfferIn.model_validate(reserved(*status)).reservation_legs == count


def test_ingest_stores_the_count_and_a_recapture_with_no_reservation_sets_0(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [reserved("required", "included", None)])["created"] == 1
    assert counts(sessions) == [("Sparpreis", 1)]
    assert post(client, auth, trip_id, [reserved(None, None, None)])["unchanged"] == 1   # the same price
    assert counts(sessions) == [("Sparpreis", 0)]
    post(client, auth, trip_id, [reserved("required", "required", None, price="79.90")])  # a new price
    assert counts(sessions) == [("Sparpreis", 2)]


def test_an_unknown_status_is_a_rejected_offer_and_the_batch_continues(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    got = post(client, auth, trip_id, [reserved("maybe", fare="Bad"), reserved("required", fare="Good")])
    assert got["rejected"] == 1 and got["created"] == 1
    assert counts(sessions) == [("Good", 1)]


def test_the_score_and_the_trip_page_do_not_change(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [reserved(None, None, None)])
    before = client.get(f"/trips/{trip_id}").text
    post(client, auth, trip_id, [reserved("required", "required", "required")])
    after = client.get(f"/trips/{trip_id}").text
    assert "reservation required" in after and "reservation required" not in before   # the mark of #1624
    assert before.count("= €") == after.count("= €") and [x for x in before.split() if x.startswith("€")] == \
        [x for x in after.split() if x.startswith("€")]


def test_migration_0033_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("fares")}
        assert "reservation_legs" in cols()
        command.downgrade(cfg, "0032")
        assert "reservation_legs" not in cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()

