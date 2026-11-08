"""The split tickets on the trip page (#1179)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Fare, Itinerary, Leg, Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)

T0 = datetime(2027, 3, 1, 7, 0, tzinfo=timezone.utc)


def _offer(s, trip_id, frm, to, depart_h, hours, price, source="db"):
    depart = T0 + timedelta(hours=depart_h)
    arrive = depart + timedelta(hours=hours)
    it = Itinerary(trip_id=trip_id, fingerprint=f"{frm}{to}{depart_h}{source}", mode_summary="train",
                   depart_at=depart, arrive_at=arrive, duration_min=int(hours * 60), transfers=0)
    it.legs = [Leg(seq=0, mode="train", from_name=frm, to_name=to, depart_at=depart, depart_offset_min=60,
                   arrive_at=arrive, arrive_offset_min=60)]
    it.fares = [Fare(source=source, latest_price=Decimal(price), currency="EUR", latest_captured_at=datetime.now(
        timezone.utc))]
    s.add(it)


def _split(c, sessions, trip_id):
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.title, trip.origin_text, trip.destination_text = "Amsterdam → Zürich", "Amsterdam", "Zürich"
        s.commit()
    c.post(f"/trips/{trip_id}/split", data={"via": "Köln"}, headers={"X-CSRF-Token": _csrf(c, "/settings")})
    with sessions() as s:
        return [t.id for t in s.get(Trip, trip_id).split_trips]


def test_the_section_shows_the_best_pair_and_the_difference(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    a, b = _split(c, sessions, trip_id)
    with sessions() as s:
        _offer(s, trip_id, "Amsterdam", "Zürich", 0, 8, "200")
        _offer(s, a, "Amsterdam", "Köln", 0, 3, "40", "ns")
        _offer(s, b, "Köln", "Zürich", 4, 5, "50", "db")
        s.commit()
    page = c.get(f"/trips/{trip_id}").text
    assert "Split tickets via Köln" in page
    assert "Amsterdam → Köln (ns)" in page and "Köln → Zürich (db)" in page
    assert "1 h 00 min transfer" in page
    assert "less than the best direct offer" in page
    assert f'href="/trips/{a}"' in page and f'href="/trips/{b}"' in page
    rows = c.get(f"/trips/{trip_id}", headers={"HX-Request": "true"}).text
    assert 'id="trip-split" hx-swap-oob="true"' in rows and "Split tickets via Köln" in rows


def test_a_part_with_no_offers_shows_no_offers_yet(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    _split(c, sessions, trip_id)
    page = c.get(f"/trips/{trip_id}").text
    assert page.count(": No offers yet.") == 2 and "Split tickets via Köln" in page


def test_a_trip_with_no_split_has_no_section(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert "Split tickets via" not in c.get(f"/trips/{trip_id}").text
