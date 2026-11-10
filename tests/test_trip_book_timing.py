"""The trip page shows the card "When to book on this route" from this trip and the older trips of its route (#1916)."""

import re
from datetime import date

from sqlalchemy import select

from app.models import Itinerary, Leg, Trip
from tests.test_book_timing import DEPART
from tests.test_book_timing import _offer as _bare_offer
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

CARD = r'<section class="book-timing card".*?</section>'


def _offer(s, t, prices):
    """One fare with a leg (the trip page needs a leg of each itinerary)."""
    _bare_offer(s, t, prices)
    it = s.scalars(select(Itinerary).where(Itinerary.trip_id == t.id).order_by(Itinerary.id.desc())).first()
    it.legs.append(Leg(seq=0, mode="train", carrier="NS", service_no="1", from_name="Amsterdam", to_name="Zürich",
                       depart_at=DEPART, depart_offset_min=0, arrive_at=DEPART, arrive_offset_min=0))
    s.flush()


def _route(sessions, trip_id):
    with sessions() as s:
        t = s.get(Trip, trip_id)
        t.origin_text, t.destination_text, t.date_from = "Amsterdam", "Zürich", date(2026, 12, 10)
        s.commit()


def _older(s, destination):
    old = Trip(title="old", origin_text="Amsterdam", destination_text=destination, date_from=date(2025, 12, 10))
    s.add(old)
    s.flush()
    return old


def test_this_trip_and_an_older_trip_of_the_route_give_3_rows(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    _route(sessions, trip_id)
    with sessions() as s:
        _offer(s, s.get(Trip, trip_id), [(3, "89.90"), (20, "70.00")])
        _offer(s, s.get(Trip, trip_id), [(2, "95.00")])
        _offer(s, _older(s, "Zurich"), [(40, "60.00")])
        _offer(s, _older(s, "Berlin"), [(100, "10.00"), (5, "1.00")])  # another route: does not count
        s.commit()
    section = re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S)
    assert section is not None
    rows = re.findall(r"<li>(.*?)</li>", section.group(0))
    assert rows == ["0–7 days before · lowest €89.90", "15–30 days before · lowest €70.00",
                    "31–60 days before · lowest €60.00"]


def test_more_than_90_days(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    _route(sessions, trip_id)
    with sessions() as s:
        _offer(s, s.get(Trip, trip_id), [(120, "50.00")])
        s.commit()
    assert "more than 90 days before · lowest €50.00" in client.get(f"/trips/{trip_id}").text


def test_a_trip_with_no_capture_has_no_card(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    _route(sessions, trip_id)
    assert 'id="book-timing"' not in client.get(f"/trips/{trip_id}").text


def without_book_timing(page: str) -> str:
    """The page with no "When to book" card: for the tests of the table, which read the whole page."""
    return re.sub(CARD, "", page, flags=re.S)
