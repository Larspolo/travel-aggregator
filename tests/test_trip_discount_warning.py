"""The trip page warns when its fares use different discount cards (#1751)."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Capture, Itinerary
from tests.test_share import share
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

WARNING = "These fares use different discount cards: BahnCard 50, none"


def _add(client, auth, trip_id, sessions, price, service_no, cards, fare="Sparpreis"):
    """One capture of one offer, with the cards `cards` (None = not known)."""
    ingest(client, auth, trip_id, [offer(price, service_no, fare=fare)])
    with sessions() as s:
        capture = s.scalars(select(Capture).order_by(Capture.id.desc())).first()
        capture.discounts = cards
        s.commit()


def _hide(sessions, trip_id, service_no):
    with sessions() as s:
        for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)):
            if it.legs[0].service_no == service_no:
                it.hidden = True
        s.commit()


def test_a_bahncard_capture_and_a_capture_with_no_card_show_the_warning(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _add(client, auth, trip_id, sessions, "59.90", "ICE 105", ["BahnCard 50"])
    _add(client, auth, trip_id, sessions, "89.90", "ICE 123", [])
    page = client.get(f"/trips/{trip_id}").text
    assert WARNING in page
    assert '<span class="muted cards">BahnCard 50</span>' in page  # the fare name does not have the card


def test_the_read_only_link_shows_the_same_warning(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _add(client, auth, trip_id, sessions, "59.90", "ICE 105", ["BahnCard 50"])
    _add(client, auth, trip_id, sessions, "89.90", "ICE 123", [])
    assert WARNING in TestClient(app).get(share(client, trip_id)).text


def test_one_card_set_and_unknown_captures_show_no_warning(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _add(client, auth, trip_id, sessions, "59.90", "ICE 105", ["BahnCard 50"], fare="Sparpreis BahnCard 50")
    _add(client, auth, trip_id, sessions, "69.90", "ICE 123", ["BahnCard 50"])
    _add(client, auth, trip_id, sessions, "89.90", "ICE 999", None)
    page = client.get(f"/trips/{trip_id}").text
    assert "different discount cards" not in page
    assert '<span class="muted cards">' in page  # only the fare whose name has no card name
    assert page.count('<span class="muted cards">') == 1


def test_a_hidden_fare_does_not_count(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _add(client, auth, trip_id, sessions, "59.90", "ICE 105", ["BahnCard 50"])
    _add(client, auth, trip_id, sessions, "89.90", "ICE 123", [])
    _hide(sessions, trip_id, "ICE 123")
    assert "different discount cards" not in client.get(f"/trips/{trip_id}?show_hidden=true").text
