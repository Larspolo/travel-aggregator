"""The price history and the compare page use the one money format of the trip page: '€78.00', 'CHF 120.00' (#661)."""

from decimal import Decimal

from sqlalchemy import select

from app.models import Fare, Itinerary
from tests.test_price_history import _add_later_price, _itinerary_id
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return {i.duration_min: i.id for i in its}  # 472: offer, 240: direct


def test_history_fragment_shows_the_euro_symbol_in_table_and_chart(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    it = _itinerary_id(sessions, trip_id)
    _add_later_price(sessions, it, "78.00")
    r = client.get(f"/trips/{trip_id}/itineraries/{it}/history", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "low €78.00" in r.text and "high €89.90" in r.text  # the chart labels
    assert "€78.00" in r.text.split('<table class="history">')[1]  # the table
    assert "€89.90" in r.text.split('<table class="history">')[1]
    assert "EUR 78.00" not in r.text and "EUR 89.90" not in r.text


def test_compare_page_shows_the_euro_symbol(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [ids[472], ids[240]]}).text
    assert "€80.90" in page and "€150.00" in page
    assert "EUR " not in page


def test_compare_page_keeps_the_code_for_a_currency_without_a_symbol(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    with sessions() as s:
        for f in s.scalars(select(Fare).where(Fare.itinerary_id == ids[472])):
            f.currency, f.latest_price = "CHF", Decimal("120.00")
        s.commit()
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [ids[472], ids[240]]}).text
    assert "CHF 120.00" in page
    assert "€89.90" not in page
