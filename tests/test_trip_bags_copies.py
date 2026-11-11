"""The checked bag of a trip in the next trip, the copy and the score of a second trip (#2415, part of #2396)."""

import re

from sqlalchemy.orm import Session

from app.models import Trip
from tests.test_trip_bags_score import _flight
from tests.test_trip_forms import client, engine  # noqa: F401  (fixtures)
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _new(engine, **kw):  # noqa: F811
    with Session(engine) as s:
        t = Trip(title="Amsterdam", origin_text="Amsterdam", destination_text="Berlin", travelers=1, **kw)
        s.add(t)
        s.commit()
        return t.id


def _token(client, path):  # noqa: F811
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _bag(engine, tid):  # noqa: F811
    with Session(engine) as s:
        return s.get(Trip, tid).checked_bag


def _new_id(r):
    return int(r.headers["location"].split("/")[2])


def test_the_next_trip_and_the_copy_of_a_none_trip_keep_none(engine, client):  # noqa: F811
    tid = _new(engine, checked_bag="none")
    token = _token(client, f"/trips/{tid}/edit")
    r = client.post(f"/trips/{tid}/next", data={"csrf_token": token}, follow_redirects=False)
    assert _bag(engine, _new_id(r)) == "none"
    r = client.post(f"/trips/{tid}/copy", data={"csrf_token": token}, follow_redirects=False)
    assert _bag(engine, _new_id(r)) == "none"


def test_the_next_trip_of_a_trip_with_no_value_has_no_bag(engine, client):  # noqa: F811
    tid = _new(engine)
    token = _token(client, f"/trips/{tid}/edit")
    r = client.post(f"/trips/{tid}/next", data={"csrf_token": token}, follow_redirects=False)
    assert _bag(engine, _new_id(r)) is None


def test_a_second_trip_without_a_value_keeps_the_bag_estimate(trip, sessions):  # noqa: F811
    client, auth, first = trip  # noqa: F811
    with sessions() as s:
        t2 = Trip(title="Amsterdam – Berlin", origin_text="Amsterdam", destination_text="Berlin")
        s.add(t2)
        s.commit()
        second = t2.id
    ingest(client, auth, first, [_flight("100.00", "KL 1")])
    ingest(client, auth, second, [_flight("100.00", "KL 1")])
    with sessions() as s:
        s.get(Trip, first).checked_bag = "none"
        s.commit()
    page = client.get(f"/trips/{first}?baggage_fee=40").text
    assert "€0 no checked bag (trip)" in page and "baggage (estimate)" not in page
    page = client.get(f"/trips/{second}?baggage_fee=40").text
    assert "baggage (estimate)" in page and "no checked bag (trip)" not in page
