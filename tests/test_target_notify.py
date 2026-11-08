"""A message when a capture brings a fare to or below the target price of its trip (#848). A test double replaces
the POST: no request leaves the test."""

import copy
from decimal import Decimal

import pytest

from app import notify
from app.models import Itinerary, Setting, Trip
from tests.test_settings_page import _token  # noqa: F401
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)
from tests.test_trip_page import BODY, ingest, offer, trip  # noqa: F401  (trip is a fixture)

URL = "https://ntfy.example/topic"


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append((url, text, headers)))
    return calls


def _setup(sessions, trip_id, channel="ntfy", target="80.00"):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.get(Trip, trip_id).target_price = None if target is None else Decimal(target)
        s.commit()


def _title(call):
    return call[2]["Title"].encode("latin-1").decode()


def test_crossings_of_the_target_send_one_message_each(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("95.00")])
    assert sent == []
    ingest(client, auth, trip_id, [offer("78.00")])
    assert len(sent) == 1
    assert _title(sent[0]).startswith("Target price: ") and sent[0][2]["Click"].endswith(f"/trips/{trip_id}")
    assert "EUR 95.00" in sent[0][1] and "EUR 78.00" in sent[0][1]
    for price in ("78.00", "76.00"):
        ingest(client, auth, trip_id, [offer(price)])
    assert len(sent) == 1
    ingest(client, auth, trip_id, [offer("85.00")])
    ingest(client, auth, trip_id, [offer("79.00")])
    assert len(sent) == 2


def test_a_new_fare_below_the_target_crosses(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("70.00")])
    assert len(sent) == 1 and "Target price" in _title(sent[0])


def test_a_pinned_drop_that_crosses_gives_one_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("95.00")])
    with sessions() as s:
        for it in s.query(Itinerary).filter_by(trip_id=trip_id):
            it.pinned = True
        s.commit()
    ingest(client, auth, trip_id, [offer("78.00")])
    assert len(sent) == 1 and len(sent[0][1].splitlines()) == 1 and "Target price" in _title(sent[0])


@pytest.mark.parametrize("case", ["no target", "none", "hidden", "no rate"])
def test_no_target_message(trip, sessions, sent, case):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id, "none" if case == "none" else "ntfy", None if case == "no target" else "80.00")
    ingest(client, auth, trip_id, [offer("95.00")])
    if case == "hidden":
        with sessions() as s:
            for it in s.query(Itinerary).filter_by(trip_id=trip_id):
                it.hidden = True
            s.commit()
    second = offer("78.00")
    if case == "no rate":
        second["price_currency"] = "XYZ"
    ingest(client, auth, trip_id, [second])
    assert sent == []


def _post(client, auth, trip_id, price):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[offer(price)])
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    return r.json()


def test_a_failed_send_does_not_change_the_response(trip, sessions, monkeypatch):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("95.00")])
    ok = _post(client, auth, trip_id, "90.00")

    def fail(url, text, headers):
        raise TimeoutError("timed out")

    monkeypatch.setattr(notify, "post", fail)
    bad = _post(client, auth, trip_id, "78.00")
    assert bad == ok
