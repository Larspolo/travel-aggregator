"""The CO₂ estimate in the expanded row of each offer (#1418)."""

import copy
import re

from sqlalchemy import select

from app.models import Itinerary
from tests.test_compare_tradeoff import timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def flight(price, hours, service):
    o = copy.deepcopy(timed(price, hours, service))
    o["legs"][0]["mode"] = "flight"
    return o


def _order(page):
    return [int(i) for i in re.findall(r'<tr id="it-(\d+)">', page)]


def test_flight_of_two_hours_shows_180_kg_and_keeps_the_order(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [flight("100.00", 2, "LX 1"), timed("90.00", 5, "ICE 2")])
    page = client.get(f"/trips/{trip_id}").text
    assert page.count("CO₂ about 180 kg per traveler (estimate)") == 1
    with sessions() as s:
        ids = {i.duration_min: i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}
    assert _order(page)[:2] == [ids[300], ids[120]]  # the cheaper train stays first: price per kg €0


def test_flight_kg_per_hour_changes_the_number(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [flight("100.00", 2, "LX 1")])
    page = client.get(f"/trips/{trip_id}", params={"co2_flight_kg_h": "100"}).text
    assert "CO₂ about 200 kg per traveler (estimate)" in page
