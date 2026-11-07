"""The whole door-to-door feature (#94): a flight and a train of one trip on the page (#100)."""

from decimal import Decimal

from app.models import AccessTime
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _flight(price):
    """Schiphol 09:00 → Zürich Flughafen 10:00: 1 hour, no transfer."""
    o = direct(price)
    o["legs"][0].update(mode="flight", carrier="KLM", service_no="KL 1953", from_name="Amsterdam Schiphol",
                        to_name="Zürich Flughafen", arrive_at="2026-12-20T10:00:00+01:00")
    return o


def test_flight_and_train_door_to_door(sessions, trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), _flight("120.00")])  # train: 4 h, €150

    page = client.get(f"/trips/{trip_id}?airport_before_min=0&airport_after_min=0").text
    assert "€150 price + €60 time = €210" in page
    assert "€120 price + €15 time = €135" in page
    assert page.index("= €135") < page.index("= €210")  # no places, no buffer: the flight first

    with sessions() as s:
        s.add_all([AccessTime(place_text="Amsterdam Schiphol", kind="access", minutes=90, cost=Decimal("0")),
                   AccessTime(place_text="Zürich Flughafen", kind="egress", minutes=40, cost=Decimal("6"))])
        s.commit()
    page = client.get(f"/trips/{trip_id}").text
    # 120 + 15 + 22.50 access + 10 egress + 6 + 37.50 airport (150 min) = 211
    assert ("€120 price + €15 time + €22.50 access time + €10 egress time + €6 egress cost + €37.50 airport time"
            " = €211") in page
    assert "€150 price + €60 time = €210" in page
    assert page.index("= €210") < page.index("= €211")  # the train first
