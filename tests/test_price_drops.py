"""The box "Price drops" of the trip page (#355): a pinned fare that became cheaper after the last view."""

import re

from alembic import command
from sqlalchemy import create_engine, inspect

from app.models import Fare, Itinerary
from tests.test_trip_booked import _alembic
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _token(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def _pin(client, sessions, trip_id, service_no, token):
    with sessions() as s:
        it = next(i for i in s.query(Itinerary).filter_by(trip_id=trip_id).all()
                  if i.legs[0].service_no == service_no)
        it_id = it.id
    r = client.post(f"/trips/{trip_id}/itineraries/{it_id}/pin", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    return it_id


def _seen(sessions):
    with sessions() as s:
        return sorted(str(f.seen_price) for f in s.query(Fare).all())


def test_a_drop_of_a_pinned_fare_shows_once(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    _pin(client, sessions, trip_id, "ICE 105", _token(client, trip_id))
    client.get(f"/trips/{trip_id}")  # the view stores the seen price
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105")])
    page = client.get(f"/trips/{trip_id}").text
    assert "Price drops" in page
    assert "price dropped EUR 20.00" in page and "now EUR 79.90" in page
    assert "Price drops" not in client.get(f"/trips/{trip_id}").text


def test_an_htmx_get_does_not_change_the_seen_price(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    _pin(client, sessions, trip_id, "ICE 105", _token(client, trip_id))
    client.get(f"/trips/{trip_id}")
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105")])
    client.get(f"/trips/{trip_id}", headers={"HX-Request": "true"})
    assert _seen(sessions) == ["99.90"]
    assert "price dropped EUR 20.00" in client.get(f"/trips/{trip_id}").text


def test_no_line_for_a_rise_an_unpinned_or_hidden_fare_no_seen_price_or_a_new_currency(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("50.00", "ICE 1"), offer("60.00", "ICE 2"), offer("70.00", "ICE 3"),
                                   offer("80.00", "ICE 4")])
    token = _token(client, trip_id)  # the view sets the seen price of all fares
    _pin(client, sessions, trip_id, "ICE 1", token)
    hidden = _pin(client, sessions, trip_id, "ICE 3", token)
    _pin(client, sessions, trip_id, "ICE 4", token)
    client.post(f"/trips/{trip_id}/itineraries/{hidden}/hide", data={"csrf_token": token}, follow_redirects=False)
    client.get(f"/trips/{trip_id}")
    chf = offer("10.00", "ICE 4")
    chf["price_currency"] = "CHF"
    ingest(client, auth, trip_id, [offer("55.00", "ICE 1"), offer("40.00", "ICE 2"), offer("30.00", "ICE 3"), chf])
    assert "Price drops" not in client.get(f"/trips/{trip_id}").text
    # a fare with no seen price
    with sessions() as s:
        s.query(Fare).update({Fare.seen_price: None})
        s.commit()
    ingest(client, auth, trip_id, [offer("20.00", "ICE 1")])
    assert "Price drops" not in client.get(f"/trips/{trip_id}").text


def test_migration_0012_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def has_column():
            return "seen_price" in {c["name"] for c in inspect(engine).get_columns("fares")}
        assert has_column()
        command.downgrade(cfg, "0011")
        assert not has_column()
        command.upgrade(cfg, "head")
        assert has_column()
    finally:
        engine.dispose()
