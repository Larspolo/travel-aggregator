"""The whole berth feature through the API (#1809, epic #1807 and #1808): the ÖBB Nightjet fixture gives the seat,
couchette and sleeper fares; the trip page shows "night in a <berth>" with its value and score; empty values give the
same scores as no berth values.

The trip page shows the breakdown of the cheapest fare of an itinerary only. So each berth is shown in turn: the two
other berths get a high value, and the berth under test wins."""

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_oebb_whole import fare_capture, post
from tests.test_reservation_fee import _totals

HIGH = "500"
# berth: (its value, the breakdown line of the page, the score = price + time + transfers + value)
CASES = {
    "seat": ("-10", "€-10 night in a seat = €292.55"),
    "couchette": ("-40", "€-40 night in a couchette = €327.55"),
    "sleeper": ("-60", "€-60 night in a sleeper = €387.55"),
}


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="berth")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def ingest_nightjet(client, auth, trip_id):
    out = post(client, auth, trip_id, fare_capture())
    assert out["errors"] == []


def berths(values):
    """The query string of the three berth values; an empty string is an empty value."""
    return "&".join(f"night_{b}_adjust={v}" for b, v in values.items())


def breakdowns(page):
    """The breakdown lines that name a berth."""
    return [line for line in page.split("\n") if "night in a" in line]


def test_each_berth_shows_its_value_and_score_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest_nightjet(client, auth, trip_id)
    for berth, (value, line) in CASES.items():
        others = {b: HIGH for b in CASES if b != berth}
        page = client.get(f"/trips/{trip_id}?{berths({**others, berth: value})}").text
        assert len(breakdowns(page)) == 1 and line in breakdowns(page)[0], (berth, breakdowns(page))


def test_the_three_fares_are_on_the_trip_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest_nightjet(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert "oebbtickets.at: Seat" in page and "oebbtickets.at: Couchette" in page and "oebbtickets.at: Sleeper" in page


def test_with_empty_berth_values_every_score_is_the_same_as_without_berth_values(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest_nightjet(client, auth, trip_id)
    none = client.get(f"/trips/{trip_id}").text
    empty = client.get(f"/trips/{trip_id}?{berths({b: '' for b in CASES})}").text
    assert _totals(empty) == _totals(none) and _totals(none)
    assert not breakdowns(empty)
