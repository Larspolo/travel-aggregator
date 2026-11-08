"""The booking fee of the source of a fare is a part of its effective cost (#1143)."""

import copy
from datetime import datetime, timezone
from decimal import Decimal

from app.models import SourceFee, Trip
from tests.test_ingest_api import BODY
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _ingest(client, auth, trip_id, source, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=offers)
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _set_fee(sessions, source, amount):
    with sessions() as s:
        s.add(SourceFee(source=source, amount=Decimal(amount), updated_at=datetime.now(timezone.utc)))
        s.commit()


def _set_travelers(sessions, trip_id, travelers):
    with sessions() as s:
        s.get(Trip, trip_id).travelers = travelers
        s.commit()


def _fare(price):
    o = direct(price)
    o.update(fare_name="Sparpreis", flexibility=None)
    return o


def test_a_trainline_fee_is_a_part_and_adds_to_the_total(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_fee(sessions, "thetrainline.com", "1.50")
    _ingest(client, auth, trip_id, "thetrainline.com", [_fare("89.00")])
    page = client.get(f"/trips/{trip_id}").text
    # 89.00 price + 60 time (4 h at 15/h) + 1.50 fee = 150.50
    assert "€1.50 Trainline fee" in page
    assert "€89 price + €60 time + €1.50 Trainline fee = €150.50" in page


def test_a_fee_adds_nothing_to_another_source(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_fee(sessions, "thetrainline.com", "1.50")
    _ingest(client, auth, trip_id, "bahn.de", [_fare("89.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert "€89 price + €60 time = €149" in page
    assert "Trainline fee" not in page


def test_the_fee_is_split_over_the_travelers(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_fee(sessions, "thetrainline.com", "1.50")
    _set_travelers(sessions, trip_id, 2)
    _ingest(client, auth, trip_id, "thetrainline.com", [_fare("89.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert "€0.75 Trainline fee" in page


def test_a_fee_of_zero_adds_no_part(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id, "thetrainline.com", [_fare("89.00")])
    without = client.get(f"/trips/{trip_id}").text
    _set_fee(sessions, "thetrainline.com", "0")
    with_zero = client.get(f"/trips/{trip_id}").text
    assert "Trainline fee" not in with_zero
    assert "€89 price + €60 time = €149" in with_zero
    assert "€149" in without and "€149" in with_zero
