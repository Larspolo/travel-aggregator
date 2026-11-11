"""A booking fee changes the main fare of a merged itinerary on each ranked page (#1144, epic #1141): one ICE from
bahn.de and from Trainline is one itinerary, and the fee of Trainline decides which fare is its main fare."""

import copy
import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary, SourceFee
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)

BAHN, TRAINLINE = "bahn.de", "thetrainline.com"
BAHN_PRICE, TRAINLINE_PRICE = "90.00", "89.00"
# the fixture ICE: 118 € of time and 10 € for its one transfer; the fare decides the main breakdown
MAIN_WITH_FEE = "€90 price + €118 time + €10 transfers = €218"  # bahn.de, the Trainline fare costs 218.50
MAIN_WITHOUT_FEE = "€89 price + €118 time + €10 transfers = €217"  # Trainline, no fee


def _ingest(client, auth, trip_id, source, price, service_no="ICE 121"):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=[offer(price, service_no, "DB Fernverkehr AG")])
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _set_fee(sessions, amount):
    with sessions() as s:
        fee = s.get(SourceFee, TRAINLINE) or SourceFee(source=TRAINLINE)
        fee.amount, fee.updated_at = Decimal(amount), datetime.now(timezone.utc)
        s.add(fee)
        s.commit()


def _merged(client, auth, trip_id, sessions, fee):
    """One ICE from both sources with the given Trainline fee; returns the ingest response of the Trainline capture."""
    _set_fee(sessions, fee)
    _ingest(client, auth, trip_id, BAHN, BAHN_PRICE)
    result = _ingest(client, auth, trip_id, TRAINLINE, TRAINLINE_PRICE)
    with sessions() as s:
        assert len(s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()) == 1
    return result


def _main_row(page):
    """The main row of the trip table: everything before its first details row (#114)."""
    return page[:page.index('<tr class="detail">')]


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def _share_link(client, trip_id):
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": _csrf(client, trip_id)})
    assert r.status_code == 200
    return re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1).removeprefix("http://testserver")


def _csv_fares(text):
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    head = rows[0]
    return {row[head.index("source")]: row[head.index("latest_price")] for row in rows[1:]}


def _ids(sessions, trip_id):
    with sessions() as s:
        return [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id))]


def test_a_trainline_fee_of_1_50_makes_the_bahn_fare_the_main_fare(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _merged(client, auth, trip_id, sessions, "1.50")
    trip_page = client.get(f"/trips/{trip_id}").text
    share_page = client.get(_share_link(client, trip_id)).text
    csv_text = client.get(f"/trips/{trip_id}/export.csv").text
    # Trainline costs 89.00 + 1.50 fee: the bahn.de fare (90.00) is the main one
    assert MAIN_WITH_FEE in _main_row(trip_page) and "Trainline fee" not in _main_row(trip_page)
    assert MAIN_WITH_FEE in share_page
    # the CSV export has no main-fare column: it keeps each fare at its own price (#701)
    assert _csv_fares(csv_text) == {BAHN: BAHN_PRICE, TRAINLINE: TRAINLINE_PRICE}


def test_a_fee_of_zero_makes_the_trainline_fare_the_main_fare(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _merged(client, auth, trip_id, sessions, "0")
    trip_page = client.get(f"/trips/{trip_id}").text
    share_page = client.get(_share_link(client, trip_id)).text
    assert MAIN_WITHOUT_FEE in _main_row(trip_page) and "Trainline fee" not in trip_page
    assert MAIN_WITHOUT_FEE in share_page


def test_the_ingest_response_best_follows_the_fee(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    assert _merged(client, auth, trip_id, sessions, "1.50")["best"]["price"] == BAHN_PRICE
    assert _merged(client, auth, trip_id, sessions, "0")["best"]["price"] == TRAINLINE_PRICE


def test_the_compare_view_follows_the_fee(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _merged(client, auth, trip_id, sessions, "1.50")
    _ingest(client, auth, trip_id, BAHN, "150.00", service_no="ICE 999")  # a second itinerary for the compare view
    merged, other = _ids(sessions, trip_id)[:2]
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [merged, other]}).text
    assert MAIN_WITH_FEE in page and MAIN_WITHOUT_FEE not in page
    assert '<td class="price best">€90.00' in page  # the bahn.de fare is the best price of the merged itinerary
    _set_fee(sessions, "0")
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [merged, other]}).text
    assert MAIN_WITHOUT_FEE in page and MAIN_WITH_FEE not in page
    assert '<td class="price best">€89.00' in page
