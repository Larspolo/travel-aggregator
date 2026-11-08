"""The fares at the target price on the trips list and the trip page (#847)."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import CurrencyRate, Fare, Itinerary, Trip
from app.target import at_target
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _target(sessions, trip_id, value="80.00"):
    with sessions() as s:
        s.get(Trip, trip_id).target_price = Decimal(value) if value else None
        s.commit()


def _fare(s, price):
    return s.scalars(select(Fare).where(Fare.latest_price == Decimal(price))).one()


def _card(html):
    start = html.find('id="at-target"')
    return html[start:html.find("</section>", start)] if start >= 0 else ""


def test_the_list_marks_the_trip_and_the_card_lists_the_cheapest_first(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("95.00", "ICE 1"), offer("80.00", "ICE 2"), offer("78.00", "ICE 3")])
    _target(sessions, trip_id)
    assert "at target" in client.get("/").text
    card = _card(client.get(f"/trips/{trip_id}").text)
    assert "At your target price" in card and "€95.00" not in card
    assert card.index("€78.00") < card.index("€80.00")
    with sessions() as s:
        assert [f.price for f in at_target(s, s.get(Trip, trip_id))] == [Decimal("78.00"), Decimal("80.00")]
        assert f'href="#it-{_fare(s, "78.00").itinerary_id}"' in card


def test_no_target_gives_no_mark_and_no_card(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("50.00", "ICE 1")])
    assert "at target" not in client.get("/").text
    assert _card(client.get(f"/trips/{trip_id}").text) == ""


def test_a_hidden_fare_and_a_fare_with_no_rate_give_no_mark(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("50.00", "ICE 1"), offer("60.00", "ICE 2"), offer("95.00", "ICE 3")])
    _target(sessions, trip_id)
    with sessions() as s:
        s.get(Itinerary, _fare(s, "50.00").itinerary_id).hidden = True
        _fare(s, "60.00").currency = "CZK"  # no rate
        s.commit()
    assert "at target" not in client.get("/").text
    assert _card(client.get(f"/trips/{trip_id}").text) == ""


def test_a_chf_fare_under_the_target_shows_its_chf_price(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("70.00", "ICE 1")])
    _target(sessions, trip_id)
    with sessions() as s:
        _fare(s, "70.00").currency = "CHF"
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("1.07"), updated_at=datetime(2026, 11, 1, tzinfo=UTC)))
        s.commit()  # CHF 70.00 is EUR 74.90
    assert "at target" in client.get("/").text
    card = _card(client.get(f"/trips/{trip_id}").text)
    assert "CHF" in card and "70.00" in card
