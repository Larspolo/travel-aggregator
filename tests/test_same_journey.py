"""The join of two itineraries of one trip (#2144): app/same_journey.py join() and split(), the ingest of a joined
row, the trip page and the export, and the migration 0053."""

import copy
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine, func, inspect, select

from app.ingest import upsert_offers
from app.models import Fare, FarePrice, Itinerary, Trip
from app.same_journey import JoinError, join, split
from app.schemas import IngestIn
from tests.test_ingest_api import BODY
from tests.test_reparse import setup  # noqa: F401, F811  (fixture: logged-in client)
from tests.test_trip_booked import _alembic

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def offer(service="ICE 105", fare_name="Sparpreis", price="89.90"):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    o = b["offers"][0]
    o["price_amount"], o["fare_name"] = price, fare_name
    o["legs"][0]["service_no"] = service
    return IngestIn(**b).offers[0]


A = dict(service="ICE 105", fare_name="Sparpreis", price="89.90")
B = dict(service="ICE 9105", fare_name="Flexpreis", price="120.00")


def make_trip(s, title="join"):
    trip = Trip(title=title)
    s.add(trip)
    s.commit()
    return trip.id


def store(s, trip_id, *offers, at=T1):
    upsert_offers(s, trip_id, None, list(offers), source="bahn.de", captured_at=at)
    s.commit()


def rows(s, trip_id):
    """The itineraries of the trip by their first service number."""
    its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
    return {sorted(it.legs, key=lambda leg: leg.seq)[0].service_no: it for it in its}


def pair(s, trip_id, a=A, b=B):
    store(s, trip_id, offer(**a), offer(**b))
    r = rows(s, trip_id)
    return r[a["service"]], r[b["service"]]


def prices(fare):
    return sorted(p.price for p in fare.prices)


def test_join_ingest_and_split(sessions):
    with sessions() as s:
        trip_id = make_trip(s)
        a, b = pair(s, trip_id)
        price_rows = s.scalar(select(func.count()).select_from(FarePrice))
        join(s, a, b)
        s.commit()
        a_id, b_id = a.id, b.id
    with sessions() as s:
        a, b = s.get(Itinerary, a_id), s.get(Itinerary, b_id)
        assert sorted(f.fare_name for f in a.fares) == ["Flexpreis", "Sparpreis"] and b.fares == []
        assert b.merged_into_id == a_id
        assert s.scalar(select(func.count()).select_from(FarePrice)) == price_rows
        # an ingest of the offer of B: a price row on its fare on A, and no new itinerary
        store(s, trip_id, offer(**{**B, "price": "99.00"}), at=T2)
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == trip_id)) == 2
        a, b = s.get(Itinerary, a_id), s.get(Itinerary, b_id)
        flex = next(f for f in a.fares if f.fare_name == "Flexpreis")
        assert prices(flex) == [Decimal("99.00"), Decimal("120.00")] and flex.latest_price == Decimal("99.00")
        assert prices(next(f for f in a.fares if f.fare_name == "Sparpreis")) == [Decimal("89.90")]
        split(s, a, b)
        s.commit()
    with sessions() as s:
        a, b = s.get(Itinerary, a_id), s.get(Itinerary, b_id)
        assert b.merged_into_id is None
        assert [f.fare_name for f in a.fares] == ["Sparpreis"] and [f.fare_name for f in b.fares] == ["Flexpreis"]
        assert prices(b.fares[0]) == [Decimal("99.00"), Decimal("120.00")] and b.fares[0].moved_from_id is None
        # after the split, an ingest of B goes to B again
        store(s, trip_id, offer(**{**B, "price": "98.00"}), at=T2)
    with sessions() as s:
        assert prices(s.get(Itinerary, b_id).fares[0])[0] == Decimal("98.00")


def test_a_new_fare_of_b_after_the_join_goes_to_a_and_back_to_b(sessions):
    with sessions() as s:
        trip_id = make_trip(s)
        a, b = pair(s, trip_id)
        join(s, a, b)
        s.commit()
        a_id, b_id = a.id, b.id
        # the fare name of A, but from the journey of B: a new fare of B on A, not the fare of A
        store(s, trip_id, offer(**{**B, "fare_name": "Sparpreis", "price": "50.00"}), at=T2)
    with sessions() as s:
        a = s.get(Itinerary, a_id)
        own = [f for f in a.fares if f.moved_from_id is None]
        assert [prices(f) for f in own] == [[Decimal("89.90")]]
        assert sorted(f.fare_name for f in a.fares if f.moved_from_id == b_id) == ["Flexpreis", "Sparpreis"]
        split(s, a, s.get(Itinerary, b_id))
        s.commit()
    with sessions() as s:
        assert sorted(f.fare_name for f in s.get(Itinerary, b_id).fares) == ["Flexpreis", "Sparpreis"]
        assert len(s.get(Itinerary, a_id).fares) == 1


def test_join_gives_the_pin_booking_and_note_of_b_to_a(sessions):
    with sessions() as s:
        trip_id = make_trip(s)
        a, b = pair(s, trip_id)
        fare = b.fares[0]
        b.pinned, b.note, b.booked, b.booked_fare_id = True, "seat 42", True, fare.id
        b.booked_price, b.booked_currency, b.booked_at = Decimal("120.00"), "EUR", T1
        s.flush()
        join(s, a, b)
        s.commit()
        assert (a.pinned, a.booked, a.booked_fare_id, a.booked_price, a.note) == (True, True, fare.id,
                                                                                 Decimal("120.00"), "seat 42")
        assert (b.pinned, b.booked, b.booked_price) == (False, False, None)
        split(s, a, b)
        s.commit()
        assert (b.booked, b.booked_fare_id, b.booked_price) == (True, fare.id, Decimal("120.00"))
        assert (a.booked, a.booked_price) == (False, None)


def test_join_refuses_two_trips_a_joined_row_and_the_same_fare(sessions):
    with sessions() as s:
        one, two = make_trip(s, "one"), make_trip(s, "two")
        a, b = pair(s, one)
        c = rows(s, two).get("ICE 105") or (store(s, two, offer(**A)) or rows(s, two)["ICE 105"])
        with pytest.raises(JoinError, match="two trips"):
            join(s, a, c)
        join(s, a, b)
        with pytest.raises(JoinError, match="joined into another row"):
            join(s, a, b)
        store(s, one, offer(service="ICE 7105"))
        d = rows(s, one)["ICE 7105"]
        with pytest.raises(JoinError, match="joined into another row"):
            join(s, b, d)
        with pytest.raises(JoinError, match="the fare bahn.de Sparpreis"):
            join(s, a, d)
        with pytest.raises(JoinError, match="itself"):
            join(s, a, a)
        with pytest.raises(JoinError, match="not joined into"):
            split(s, d, b)


def test_the_trip_page_and_the_export_show_one_row(setup, sessions):  # noqa: F811
    client, _, trip_id = setup
    with sessions() as s:
        a, b = pair(s, trip_id)
        b.pinned = True
        join(s, a, b)
        s.commit()
        a_id, b_id = a.id, b.id
    page = client.get(f"/trips/{trip_id}").text
    assert re.findall(r'<tr id="it-(\d+)"', page) == [str(a_id)]
    export = client.get(f"/trips/{trip_id}/export.json").json()
    assert len(export["itineraries"]) == 1 and len(export["itineraries"][0]["fares"]) == 2
    csv = client.get(f"/trips/{trip_id}/export.csv").text
    assert "ICE 9105" not in csv
    assert f"it-{b_id}" not in client.get("/pinned").text


def test_the_delete_of_a_trip_deletes_a_joined_pair(sessions):
    with sessions() as s:
        trip_id = make_trip(s)
        a, b = pair(s, trip_id)
        join(s, a, b)
        s.commit()
        s.delete(s.get(Trip, trip_id))
        s.commit()
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 0
        assert s.scalar(select(func.count()).select_from(Fare)) == 0


def test_migration_0053_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols(table):
            return {c["name"] for c in inspect(engine).get_columns(table)}
        assert "merged_into_id" in cols("itineraries") and "moved_from_id" in cols("fares")
        command.downgrade(cfg, "0052")
        assert "merged_into_id" not in cols("itineraries") and "moved_from_id" not in cols("fares")
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
