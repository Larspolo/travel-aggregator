"""The cancel of a booked journey and its refund in the JSON export, the import and the merge (#1688)."""

import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models import Itinerary, Leg, Trip
from app.trip_import import import_trip
from app.trip_merge import merge_trips
from app.web.export import load_trip, trip_export

UTC = timezone.utc
CANCEL_AT = datetime(2026, 11, 6, 7, 15, tzinfo=timezone(timedelta(hours=1)))
CANCEL_KEYS = ("cancelled_at", "refund_price")


def _trip(s, title, fingerprint, booked=False, cancelled=False):
    t = Trip(title=title, origin_text="Amsterdam", destination_text="Zürich",
             date_from=date(2026, 12, 1), travelers=1, status="planning")
    it = Itinerary(fingerprint=fingerprint, mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC),
                   arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), duration_min=420, transfers=0, booked=booked)
    if booked:
        it.booked_price, it.booked_currency = Decimal("150.00"), "EUR"
        it.booked_at = datetime(2026, 11, 5, 8, 30, tzinfo=UTC)
    if cancelled:
        it.booked, it.cancelled_at, it.refund_price = False, CANCEL_AT.astimezone(UTC), Decimal("120.00")
    it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                       to_name="Zürich", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC), depart_offset_min=0,
                       arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), arrive_offset_min=0))
    t.itineraries.append(it)
    s.add(t)
    s.commit()
    return t.id


def test_the_export_of_a_cancelled_booking_has_the_cancel_and_the_refund(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Cancelled", "fp-cancel", cancelled=True)
        it = trip_export(load_trip(s, trip_id))["itineraries"][0]
    assert it["cancelled_at"] == "2026-11-06T06:15:00+00:00"
    assert it["refund_price"] == "120.00"


def test_an_import_gives_the_same_cancel_and_refund(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Cancelled", "fp-cancel", cancelled=True)
        data = trip_export(load_trip(s, trip_id))
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.cancelled_at == CANCEL_AT and it.cancelled_at.utcoffset() == timedelta(0)
        assert it.refund_price == Decimal("120.00")
        assert it.booked is False


def test_an_export_from_before_the_change_imports_with_no_cancel(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Booked", "fp-booked", booked=True)
        data = trip_export(load_trip(s, trip_id))
    for key in CANCEL_KEYS:
        data["itineraries"][0].pop(key, None)
    with sessions() as s:
        r = import_trip(s, data)
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert (it.cancelled_at, it.refund_price) == (None, None)
        assert (it.booked_price, it.booked_currency) == (Decimal("150.00"), "EUR")


def test_a_merge_into_a_trip_with_no_booking_keeps_the_cancel_and_the_refund(sessions):
    with sessions() as s:
        source = _trip(s, "Source", "fp-same", cancelled=True)
        target = _trip(s, "Target", "fp-same")
    with sessions() as s:
        merge_trips(s, source, target)
    with sessions() as s:
        it = load_trip(s, target).itineraries[0]
        assert it.cancelled_at == CANCEL_AT.astimezone(UTC)
        assert it.refund_price == Decimal("120.00")


def test_a_merge_of_a_moved_cancelled_itinerary_keeps_the_cancel(sessions):
    with sessions() as s:
        source = _trip(s, "Source", "fp-only-source", cancelled=True)
        target = _trip(s, "Target", "fp-other")
    with sessions() as s:
        merge_trips(s, source, target)
    with sessions() as s:
        cancelled = [it for it in load_trip(s, target).itineraries if it.fingerprint == "fp-only-source"]
        assert len(cancelled) == 1
        assert (cancelled[0].cancelled_at, cancelled[0].refund_price) == (CANCEL_AT.astimezone(UTC), Decimal("120.00"))
