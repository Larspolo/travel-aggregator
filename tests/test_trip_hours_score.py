"""The hour value of a trip gives the time part of its offers (#2423); the other trips keep the profile value."""

import dataclasses
from decimal import Decimal
from types import SimpleNamespace

from app.door import door_extras
from app.models import Trip
from app.ranking import Breakdown, Weights, bar_parts, format_breakdown
from app.risk import mode_hour_extras
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _set_hours(sessions, trip_id, value):
    with sessions() as s:
        s.get(Trip, trip_id).hour_value = value
        s.commit()


def test_the_trip_value_replaces_the_profile_value(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    with sessions() as s:
        other = Trip(title="Amsterdam – Paris", origin_text="Amsterdam", destination_text="Paris")
        s.add(other)
        s.commit()
        other_id = other.id
    ingest(client, auth, trip_id, [direct("150.00")])
    ingest(client, auth, other_id, [direct("150.00")])
    page = client.get(f"/trips/{trip_id}?hour_markup=15").text
    assert "€60 time" in page and "€210" in page
    _set_hours(sessions, trip_id, Decimal("30"))
    page = client.get(f"/trips/{trip_id}").text
    assert "€120 time (trip)" in page and "€270" in page
    other_page = client.get(f"/trips/{other_id}").text
    assert "€60 time" in other_page and "time (trip)" not in other_page


def test_the_url_value_wins(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00")])
    _set_hours(sessions, trip_id, Decimal("30"))
    page = client.get(f"/trips/{trip_id}?hour_markup=20").text
    assert "€80 time" in page and "time (trip)" not in page


def test_the_bar_and_the_door_time_use_the_trip_value():
    b = Breakdown(price=Decimal(10), time_cost=Decimal(120), transfer_cost=Decimal(0), total=Decimal(130),
                  time_label="time (trip)")
    assert [p[0] for p in bar_parts(b)] == ["price", "time (trip)"]
    assert format_breakdown(b) == "€10 price + €120 time (trip) = €130"
    leg = SimpleNamespace(from_name="Amsterdam Centraal", to_name="X")
    place = SimpleNamespace(id=1, kind="access", place_text="Amsterdam Centraal", minutes=60, cost=0)
    extras = door_extras(SimpleNamespace(legs=[leg]), [place], Decimal("30"))
    assert extras[0] == ("access time", Decimal(30))


def test_the_mode_rate_stays_the_profile_value():
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 12, 20, 8, tzinfo=timezone.utc)
    it = SimpleNamespace(legs=[SimpleNamespace(mode="train", depart_at=start, arrive_at=start + timedelta(hours=4))])
    w = dataclasses.replace(Weights(train_hour_markup=Decimal(10)), hour_markup=Decimal(30))
    assert mode_hour_extras(it, w) == (("train hours", Decimal(-80)),)
