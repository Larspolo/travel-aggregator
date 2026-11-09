"""The scope of the route history: alias names, other currencies, hidden offers, several older trips (#1520, #1545)."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Capture, CurrencyRate, Fare, FarePrice, Itinerary
from app.route_history import route_history
from tests.test_route_history import AT, _offer, _trip
from tests.test_route_history_page import CARD, _route_of_the_trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _offer_in(s, owner, prices, currency, travelers, booked=None, hidden=False):
    """An itinerary of `owner` whose prices are in `currency`, with `travelers` on the capture."""
    it = Itinerary(trip=owner, fingerprint=f"fp{owner.id}-{currency}-{hidden}", depart_at=AT, arrive_at=AT,
                   duration_min=60, hidden=hidden)
    fare = Fare(itinerary=it, source="manual", latest_price=Decimal(prices[-1]), currency=currency,
                latest_captured_at=AT)
    s.add_all([it, fare])
    s.flush()
    cap = Capture(trip_id=owner.id, source="manual", captured_at=AT, travelers=travelers)
    s.add(cap)
    s.flush()
    for p in prices:
        s.add(FarePrice(fare=fare, price=Decimal(p), currency=currency, captured_at=AT, capture_id=cap.id))
    if booked:
        it.booked, it.booked_fare_id, it.booked_price, it.booked_currency = True, fare.id, Decimal(booked), currency
    s.flush()


def test_an_older_trip_with_the_airport_code_gives_an_entry(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        old = _trip(s, "AMS", "ZRH", date(2025, 12, 12), travelers=2)
        _offer(s, old, 1, ["98.00"], 2)
        s.commit()
        entries = route_history(s, trip)
    assert [e.trip_id for e in entries] == [old.id]


def test_an_older_trip_with_an_alias_spelling_gives_an_entry(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        old = _trip(s, "Amsterdam", "Zuerich", date(2025, 12, 12), travelers=2)
        _offer(s, old, 1, ["98.00"], 2)
        s.commit()
        entries = route_history(s, trip)
    assert [e.trip_id for e in entries] == [old.id]


def test_a_price_in_chf_with_a_rate_counts_in_eur_per_traveler(sessions):
    with sessions() as s:
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("1.05"), updated_at=datetime.now(UTC)))
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        old = _trip(s, "Amsterdam", "Zürich", date(2025, 12, 12), travelers=2)
        _offer_in(s, old, ["100.00"], "CHF", 2, booked="100.00")
        s.commit()
        (entry,) = route_history(s, trip)
    assert entry.cheapest_eur == Decimal("52.50")
    assert entry.paid_eur == Decimal("52.50")


def test_a_price_with_no_rate_gives_no_cheapest_and_no_paid(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        old = _trip(s, "Amsterdam", "Zürich", date(2025, 12, 12), travelers=2)
        _offer_in(s, old, ["100.00"], "XYZ", 2, booked="100.00")
        s.commit()
        (entry,) = route_history(s, trip)
    assert entry.cheapest_eur is None
    assert entry.paid_eur is None


def test_a_hidden_itinerary_does_not_count_for_the_cheapest_price(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        old = _trip(s, "Amsterdam", "Zürich", date(2025, 12, 12), travelers=2)
        _offer_in(s, old, ["10.00"], "EUR", 2, hidden=True)
        _offer_in(s, old, ["98.00"], "EUR", 2)
        s.commit()
        (entry,) = route_history(s, trip)
    assert entry.cheapest_eur == Decimal("49.00")


def test_six_older_trips_give_the_five_newest(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        olds = [_trip(s, "Amsterdam", "Zürich", date(2025, month, 1), travelers=2) for month in range(1, 7)]
        s.commit()
        ids = [t.id for t in olds]
        entries = route_history(s, trip)
    assert len(entries) == 5
    assert [e.trip_id for e in entries] == list(reversed(ids[1:]))  # newest first; the oldest (January) is left out
    assert ids[0] not in [e.trip_id for e in entries]


def test_the_card_lists_two_older_trips_newest_month_first(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _route_of_the_trip(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("89.90")])
    with sessions() as s:
        older = _trip(s, "Amsterdam", "Zürich", date(2025, 11, 3), travelers=2)
        newer = _trip(s, "Amsterdam", "Zürich", date(2025, 12, 12), travelers=2)
        s.commit()
        older_id, newer_id = older.id, newer.id
    section = re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S)
    assert section is not None
    html = section.group(0)
    link_newer = f'<a href="/trips/{newer_id}">2025-12</a>'
    link_older = f'<a href="/trips/{older_id}">2025-11</a>'
    assert link_newer in html and link_older in html
    assert html.index(link_newer) < html.index(link_older)
