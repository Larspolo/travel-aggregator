"""Self-transfers (#176): the `ticket` of each leg, the count on the fare, the penalty in the breakdown."""

import copy
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select

from app.ingest import fingerprint
from app.models import Fare
from app.ranking import Weights
from app.risk import self_transfer_extras
from app.schemas import OfferIn
from tests.test_trip_page import BODY, offer, trip  # noqa: F401  (trip is a fixture)


def two_tickets(price="89.90", fare="Sparpreis"):
    o = offer(price, fare=fare)
    o["legs"][0]["ticket"] = 1
    o["legs"][1]["ticket"] = 2
    return o


def post(client, auth, trip_id, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=offers)
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _offer(*tickets):
    o = copy.deepcopy(BODY["offers"][0])
    legs = o["legs"]
    legs.append(dict(legs[1], from_name="Zürich HB", to_name="Chur", depart_at="2026-12-20T15:37:00+01:00",
                     arrive_at="2026-12-20T16:52:00+01:00"))
    for leg, t in zip(legs, tickets):
        leg["ticket"] = t
    return OfferIn.model_validate(o)


@pytest.mark.parametrize("tickets, count", [
    ((None, None, None), 0), ((1, 1, 1), 0), ((1, 2, 2), 1), ((1, 2, 3), 2), ((1, None, 2), 1), ((None, 2, 2), 0),
])
def test_count_of_self_transfers(tickets, count):
    assert _offer(*tickets).self_transfers == count


def test_a_ticket_number_below_1_is_rejected():
    o = two_tickets()
    o["legs"][1]["ticket"] = 0
    with pytest.raises(ValueError):
        OfferIn.model_validate(o)


def test_the_ticket_does_not_change_the_fingerprint():
    one = OfferIn.model_validate(offer("89.90"))
    two = OfferIn.model_validate(two_tickets())
    assert fingerprint(one.legs) == fingerprint(two.legs)


def test_ingest_stores_the_count_and_a_recapture_is_unchanged(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [two_tickets()])["created"] == 1
    assert post(client, auth, trip_id, [two_tickets()])["unchanged"] == 1
    with sessions() as s:
        assert s.scalar(select(Fare.self_transfers)) == 1


def test_one_journey_is_one_ticket_at_one_source_and_two_at_another(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [offer("99.00", fare="Flexpreis"), two_tickets("79.00", fare="Combo")])
    with sessions() as s:
        assert sorted(s.execute(select(Fare.fare_name, Fare.self_transfers)).all()) == [("Combo", 1), ("Flexpreis", 0)]


def test_penalty_per_self_transfer_and_zero_adds_no_part():
    fare = SimpleNamespace(self_transfers=2)
    assert self_transfer_extras(fare, Weights(self_transfer_penalty=25)) == (("self-transfer", 50),)
    assert self_transfer_extras(fare, Weights()) == ()
    assert self_transfer_extras(SimpleNamespace(self_transfers=0), Weights(self_transfer_penalty=25)) == ()


def test_trip_page_shows_the_self_transfer_part(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [two_tickets()])
    default = client.get(f"/trips/{trip_id}").text
    assert "= €217.90" in default and "self-transfer =" not in default
    page = client.get(f"/trips/{trip_id}?self_transfer_penalty=30").text
    # 89.90 + 472 min × 15/60 = 118 + 1 transfer × 10 + 30 = 247.90
    assert "€89.90 price + €118 time + €10 transfers + €30 self-transfer = €247.90" in page
    assert 'name="self_transfer_penalty"' in page and 'value="30"' in page


def test_migration_down_and_up(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    engine = create_engine(empty_database_url)
    try:
        command.upgrade(cfg, "head")
        assert "self_transfers" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0004")
        assert "self_transfers" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
