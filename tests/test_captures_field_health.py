"""The card "Empty fields by source" of the captures page (#1969): one line for each source and field of
`field_health()` with an empty fare, the stopped ones marked."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

from app.models import Fare, Itinerary, Leg, Trip
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

_ids = count()
FULL = {"service_no": "ICE 1", "carrier": "DB", "fare_name": "Flex", "travel_class": "2", "flexibility": "flex"}


def _seed(sessions, n, days_ago, **empty):
    values = {**FULL, **empty}
    now = datetime.now(timezone.utc)
    with sessions() as s:
        t = Trip(title="T", origin_text="A", destination_text="B")
        s.add(t)
        s.flush()
        for _ in range(n):
            it = Itinerary(trip_id=t.id, fingerprint=f"field-{next(_ids)}", depart_at=now, arrive_at=now,
                           duration_min=60)
            it.legs.append(Leg(seq=0, mode="train", carrier=values["carrier"], service_no=values["service_no"],
                               from_name="A", to_name="B", depart_at=now, depart_offset_min=60, arrive_at=now,
                               arrive_offset_min=60))
            it.fares.append(Fare(source="bahn.de", fare_name=values["fare_name"],
                                 travel_class=values["travel_class"], flexibility=values["flexibility"],
                                 latest_price=Decimal("10.00"), currency="EUR",
                                 latest_captured_at=now - timedelta(days=days_ago)))
            s.add(it)
        s.commit()


def test_a_stopped_field_shows_its_line_with_the_mark(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _seed(sessions, 40, 30)
    _seed(sessions, 12, 2, service_no=None)
    page = client.get("/captures").text
    assert 'id="field-health"' in page
    assert "bahn.de: no service number in 12 of 12 fares (before: 0 of 40)" in page
    assert '(before: 0 of 40) <strong class="mark">stopped</strong>' in page


def test_a_field_always_empty_shows_its_line_with_no_mark(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _seed(sessions, 40, 30, service_no=None)
    _seed(sessions, 12, 2, service_no=None)
    page = client.get("/captures").text
    assert "bahn.de: no service number in 12 of 12 fares (before: 40 of 40)</li>" in page
    assert "stopped</strong>" not in page


def test_no_card_with_failed_or_with_source(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _seed(sessions, 12, 2, service_no=None)
    assert 'id="field-health"' in client.get("/captures").text
    assert 'id="field-health"' not in client.get("/captures?failed=1").text
    assert 'id="field-health"' not in client.get("/captures?source=bahn.de").text
