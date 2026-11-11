"""The trips list shows the largest price drop of each trip (#356)."""

from decimal import Decimal

from app.drops import drops_by_trip
from app.models import Trip
from tests.test_price_drops import _pin, _token
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _other_trip(sessions):
    with sessions() as s:
        t = Trip(title="Paris", origin_text="Lyon", destination_text="Paris")
        s.add(t)
        s.commit()
        return t.id


def _view_trip(client, trip_id):
    client.get(f"/trips/{trip_id}")  # the view stores the seen price


def test_the_list_shows_the_largest_drop(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105"), offer("60.00", "ICE 7")])
    token = _token(client, trip_id)
    _pin(client, sessions, trip_id, "ICE 105", token)
    _pin(client, sessions, trip_id, "ICE 7", token)
    _view_trip(client, trip_id)
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105"), offer("50.00", "ICE 7")])
    html = client.get("/").text
    assert "price dropped €20.00" in html
    assert "price dropped €10.00" not in html


def test_the_mark_is_gone_after_the_trip_page_is_viewed(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    _pin(client, sessions, trip_id, "ICE 105", _token(client, trip_id))
    _view_trip(client, trip_id)
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105")])
    assert "price dropped €20.00" in client.get("/").text
    _view_trip(client, trip_id)
    assert "price dropped" not in client.get("/").text


def test_a_trip_without_a_drop_has_no_mark(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    other = _other_trip(sessions)
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    _pin(client, sessions, trip_id, "ICE 105", _token(client, trip_id))
    _view_trip(client, trip_id)
    ingest(client, auth, trip_id, [offer("120.00", "ICE 105")])  # a rise, not a drop
    ingest(client, auth, other, [offer("30.00", "ICE 9")])
    html = client.get("/").text
    assert "price dropped" not in html
    assert "Paris" in html


def test_drops_by_trip_returns_currency_and_largest_amount(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90", "ICE 105")])
    _pin(client, sessions, trip_id, "ICE 105", _token(client, trip_id))
    _view_trip(client, trip_id)
    ingest(client, auth, trip_id, [offer("79.90", "ICE 105")])
    with sessions() as s:
        assert drops_by_trip(s) == {trip_id: ("EUR", Decimal("20.00"))}
