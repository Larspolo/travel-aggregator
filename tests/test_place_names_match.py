"""The place names of the owner in the trip match and the trip checks (#2216, epic #2214)."""

from datetime import date

from app.duplicates import duplicate_trips
from app.models import PlaceName, Trip
from app.place_names import aliases
from app.route_history import route_history
from app.schemas import OfferIn
from app.tripmatch import best_trip, mismatch


def _offer(to_name="Parijs"):
    return OfferIn.model_validate({"price_amount": "89.90", "price_currency": "EUR", "legs": [
        {"mode": "train", "from_name": "Amsterdam Centraal", "to_name": to_name, "depart_at": "2026-12-20T07:34:00+01:00",
         "arrive_at": "2026-12-20T14:02:00+01:00"}]})


def _trip(s, destination, day=date(2026, 12, 20), status="planning"):
    trip = Trip(title=f"A {destination} {day}", origin_text="Amsterdam", destination_text=destination,
                date_from=day, status=status)
    s.add(trip)
    s.flush()
    return trip


def _row(s):
    s.add(PlaceName(city="Paris", name="Parijs"))
    s.flush()


def test_an_owner_name_removes_the_places_mismatch(sessions):
    with sessions() as s:
        trip = _trip(s, "Paris")
        assert mismatch(trip, [_offer()], aliases=aliases(s)) == "places"
        _row(s)
        assert mismatch(trip, [_offer()], aliases=aliases(s)) is None


def test_best_trip_selects_the_trip_of_the_owner_name(sessions):
    with sessions() as s:
        _row(s)
        selected = _trip(s, "Lisbon")
        paris = _trip(s, "Paris")
        assert best_trip([selected, paris], [_offer()], selected, aliases(s)) is paris
        assert best_trip([selected, paris], [_offer()], selected) is selected


def test_route_history_and_duplicates_use_the_owner_names(sessions):
    with sessions() as s:
        older = _trip(s, "Paris", day=date(2025, 6, 1))
        dup = _trip(s, "Paris")
        trip = _trip(s, "Parijs")
        s.commit()
        assert route_history(s, trip) == [] and duplicate_trips(s, trip) == []
        _row(s)
        s.commit()
        assert older.id in [r.trip_id for r in route_history(s, trip)]
        assert duplicate_trips(s, trip) == [dup]
