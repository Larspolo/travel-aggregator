"""A message when a capture lowers the price of a flexible booked fare (#1429). A test double replaces the POST."""

from decimal import Decimal

import pytest

from app.models import Itinerary
from tests.test_notify_ntfy import _channel, sent  # noqa: F401  (sent is a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

LINE = "Booked DB ICE 105, SBB IC 61: now EUR 69.00, paid EUR 89.00 (−EUR 20.00), {} fare"


def flex(price, tier="flexible", **kw):
    o = offer(price, **kw)
    o["flexibility"] = tier
    return o


def _book(sessions, trip_id, fare="Sparpreis", paid="89.00", currency="EUR"):
    with sessions() as s:
        it = s.query(Itinerary).filter_by(trip_id=trip_id).one()
        it.booked, it.booked_price, it.booked_currency = True, Decimal(paid), currency
        it.booked_fare_id = next(f.id for f in it.fares if f.fare_name == fare)
        s.commit()


@pytest.mark.parametrize("tier,label", [("flexible", "flexible"), ("partly_refundable", "partly refundable")])
def test_a_lower_price_of_a_flexible_booked_fare_sends_one_message(trip, sessions, sent, tier, label):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions)
    ingest(client, auth, trip_id, [flex("89.00", tier)])
    _book(sessions, trip_id)
    ingest(client, auth, trip_id, [flex("69.00", tier)])
    assert len(sent) == 1
    _, text, headers = sent[0]
    assert text == LINE.format(label)
    assert headers["Title"].encode("latin-1").decode().startswith("Booked fare cheaper: ")
    ingest(client, auth, trip_id, [flex("69.00", tier)])
    assert len(sent) == 1


@pytest.mark.parametrize("case", ["non_refundable", "no_tier", "other_fare", "same", "higher", "currency"])
def test_no_booked_message(trip, sessions, sent, case):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions)
    tier = {"non_refundable": "non_refundable", "no_tier": None}.get(case, "flexible")
    ingest(client, auth, trip_id, [flex("89.00", tier), flex("99.00", tier, fare="Flexpreis")])
    _book(sessions, trip_id, fare="Flexpreis" if case == "other_fare" else "Sparpreis",
          paid={"same": "69.00", "higher": "60.00"}.get(case, "89.00"),
          currency="CHF" if case == "currency" else "EUR")
    ingest(client, auth, trip_id, [flex("69.00", tier)])
    assert not any(text.startswith("Booked") for _, text, _ in sent)
