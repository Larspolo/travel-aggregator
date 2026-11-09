"""The trip page shows the card "Earlier trips on this route" for the older trips on the same route (#1522)."""

import re
from datetime import date

from app.models import Trip
from tests.test_route_history import _offer, _trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

CARD = r'<section class="route-history card".*?</section>'


def _route_of_the_trip(sessions, trip_id):
    """The fixture trip on the route Amsterdam to Zürich, with 2 travelers."""
    with sessions() as s:
        t = s.get(Trip, trip_id)
        t.origin_text, t.destination_text, t.date_from, t.travelers = "Amsterdam", "Zürich", date(2026, 12, 10), 2
        s.commit()


def test_an_older_trip_on_the_same_route_shows_the_card_with_its_prices_and_link(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _route_of_the_trip(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("89.90")])  # the card shows with the offers of the trip
    with sessions() as s:
        old = _trip(s, "amsterdam", "Zurich", date(2025, 12, 12), travelers=2)
        _offer(s, old, 1, ["98.00", "118.00"], 2, booked="118.00")
        s.commit()
        old_id = old.id
    section = re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S)
    assert section is not None
    assert "<h2>Earlier trips on this route</h2>" in section.group(0)
    assert f'<a href="/trips/{old_id}">2025-12</a>' in section.group(0)
    assert "cheapest €49.00 · paid €59.00" in section.group(0)


def test_an_older_trip_without_a_fare_shows_a_dash_and_no_paid_part(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _route_of_the_trip(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("89.90")])
    with sessions() as s:
        _trip(s, "Amsterdam", "Zurich", date(2025, 12, 12), travelers=2)
        s.commit()
    section = re.search(CARD, client.get(f"/trips/{trip_id}").text, re.S)
    assert section is not None
    assert "2025-12</a> · cheapest -" in section.group(0)
    assert "paid" not in section.group(0)


def test_a_trip_with_no_older_trip_on_its_route_has_no_card(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _route_of_the_trip(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("89.90")])
    with sessions() as s:
        _trip(s, "Amsterdam", "Berlin", date(2025, 10, 1))
        s.commit()
    assert 'id="route-history"' not in client.get(f"/trips/{trip_id}").text
