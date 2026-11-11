"""The fares with an implausible latest price are marked, and a later plausible price removes the mark (#1604)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models import Fare, FarePrice, Itinerary, Trip
from app.suspect import SuspectMark, implausible, suspect_fares

AT = datetime(2026, 11, 1, 12, tzinfo=UTC)


def _trip(s, title="Trip"):
    trip = Trip(title=title, origin_text="Amsterdam", destination_text="Zürich", date_from=AT.date())
    s.add(trip)
    s.flush()
    return trip


def _fare(s, trip, rows, currency="EUR", n=1):
    """A fare with one price row per (day, price, currency) in `rows`; the last row is the latest price."""
    it = Itinerary(trip=trip, fingerprint=f"fp{trip.id}-{n}", depart_at=AT, arrive_at=AT, duration_min=60)
    s.add(it)
    s.flush()
    latest_day, latest_price, latest_cur = rows[-1]
    fare = Fare(itinerary=it, source="bahn", latest_price=Decimal(latest_price), currency=latest_cur,
                latest_captured_at=datetime(2026, 11, latest_day, 12, tzinfo=UTC))
    s.add(fare)
    s.flush()
    for day, price, cur in rows:
        s.add(FarePrice(fare=fare, price=Decimal(price), currency=cur,
                        captured_at=datetime(2026, 11, day, 12, tzinfo=UTC)))
    s.flush()
    return fare


def test_a_fare_that_drops_to_a_fifth_or_rises_above_five_times_is_marked(sessions):
    with sessions() as s:
        trip = _trip(s)
        low = _fare(s, trip, [(1, "39.00", "EUR"), (2, "3.50", "EUR")], n=1)
        high = _fare(s, trip, [(1, "39.00", "EUR"), (2, "250.00", "EUR")], n=2)
        zero = _fare(s, trip, [(2, "0", "EUR")], n=3)
        s.commit()
        marks = suspect_fares(s, [trip.id])
        assert marks[low.id] == SuspectMark(Decimal("3.50"), Decimal("39.00"), "EUR")
        assert marks[high.id] == SuspectMark(Decimal("250.00"), Decimal("39.00"), "EUR")
        assert marks[zero.id] == SuspectMark(Decimal("0"), None, "EUR")


def test_a_plausible_change_or_a_later_plausible_price_gives_no_mark(sessions):
    with sessions() as s:
        trip = _trip(s)
        factor_below_five = _fare(s, trip, [(1, "39.00", "EUR"), (2, "8.00", "EUR")], n=1)
        recovered = _fare(s, trip, [(1, "39.00", "EUR"), (2, "3.50", "EUR"), (3, "41.00", "EUR")], n=2)
        first_price = _fare(s, trip, [(1, "5.00", "EUR")], n=3)
        s.commit()
        marks = suspect_fares(s, [trip.id])
        assert factor_below_five.id not in marks
        assert recovered.id not in marks
        assert first_price.id not in marks


def test_an_older_price_in_another_currency_is_no_baseline(sessions):
    with sessions() as s:
        trip = _trip(s)
        fare = _fare(s, trip, [(1, "39.00", "GBP"), (2, "3.50", "EUR")], n=1)
        s.commit()
        assert fare.id not in suspect_fares(s, [trip.id])


def test_fares_of_another_trip_are_not_in_the_result(sessions):
    with sessions() as s:
        trip = _trip(s, "one")
        other = _trip(s, "two")
        mine = _fare(s, trip, [(1, "39.00", "EUR"), (2, "3.50", "EUR")], n=1)
        theirs = _fare(s, other, [(1, "39.00", "EUR"), (2, "3.50", "EUR")], n=2)
        s.commit()
        marks = suspect_fares(s, [trip.id])
        assert mine.id in marks
        assert theirs.id not in marks


def test_no_trip_ids_give_an_empty_result(sessions):
    with sessions() as s:
        assert suspect_fares(s, []) == {}


def test_the_rule_for_one_price_pair_uses_decimal(sessions):
    assert implausible(Decimal("0"), None)
    assert implausible(Decimal("3.50"), Decimal("39.00"))
    assert implausible(Decimal("250.00"), Decimal("39.00"))
    assert not implausible(Decimal("8.00"), Decimal("39.00"))
    assert not implausible(Decimal("5.00"), None)
