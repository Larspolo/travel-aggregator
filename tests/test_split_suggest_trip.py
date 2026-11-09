"""The trip page shows the transfer places of its offers and a link to split the trip (#1460)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Fare, Itinerary, Leg, Trip
from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client)
from tests.test_share import share
from tests.test_split_page import _offer, _split

T0 = datetime(2027, 3, 1, 7, 0, tzinfo=timezone.utc)


def _via(s, trip_id, via, n, price="90"):
    """An offer Amsterdam → via → Zürich that departs n hours after T0."""
    depart = T0 + timedelta(hours=n)
    it = Itinerary(trip_id=trip_id, fingerprint=f"via{via}{n}", mode_summary="train", depart_at=depart,
                   arrive_at=depart + timedelta(hours=6), duration_min=360, transfers=1)
    it.legs = [Leg(seq=0, mode="train", from_name="Amsterdam", to_name=via, depart_at=depart, depart_offset_min=60,
                   arrive_at=depart + timedelta(hours=3), arrive_offset_min=60),
               Leg(seq=1, mode="train", from_name=via, to_name="Zürich", depart_at=depart + timedelta(hours=3),
                   depart_offset_min=60, arrive_at=depart + timedelta(hours=6), arrive_offset_min=60)]
    it.fares = [Fare(source="db", latest_price=Decimal(price), currency="EUR",
                     latest_captured_at=datetime.now(timezone.utc))]
    s.add(it)


def _trip(sessions, trip_id):
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.origin_text, trip.destination_text = "Amsterdam", "Zürich"
        s.commit()


def test_the_trip_page_shows_the_transfer_places_and_the_link(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _trip(sessions, trip_id)
    with sessions() as s:
        for n in range(3):
            _via(s, trip_id, "Köln Hbf", n)
        _via(s, trip_id, "Frankfurt(Main)Hbf", 5)
        s.commit()
    page = c.get(f"/trips/{trip_id}").text
    assert "Transfer places of these offers: Köln Hbf (3) · Frankfurt(Main)Hbf (1) ·" in page
    assert f'href="/trips/{trip_id}/edit#f-via">Split the trip</a>' in page


def test_only_direct_offers_show_no_line(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _trip(sessions, trip_id)
    with sessions() as s:
        _offer(s, trip_id, "Amsterdam", "Zürich", 0, 8, "200")
        s.commit()
    assert "Transfer places of these offers" not in c.get(f"/trips/{trip_id}").text


def test_a_split_trip_and_the_shared_page_show_no_line(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    a, _b = _split(c, sessions, trip_id)
    with sessions() as s:
        _via(s, a, "Utrecht", 0)
        _via(s, trip_id, "Köln", 1)
        _via(s, trip_id, "Utrecht", 2)
        s.commit()
    assert "Transfer places of these offers" not in c.get(f"/trips/{a}").text
    page = c.get(f"/trips/{trip_id}").text
    assert "Transfer places of these offers: Utrecht (1) ·" in page  # the via place of the split (Köln) does not show
    shared = c.get(share(c, trip_id)).text
    assert "Köln" in shared and "Transfer places of these offers" not in shared
