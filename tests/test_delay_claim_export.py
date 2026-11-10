"""The delay and the paid claim of a booked journey in the JSON export, the import and the merge (#1691, #1702)."""

import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models import Itinerary, Leg, Trip
from app.trip_import import import_trip
from app.trip_merge import merge_trips
from app.web.export import load_trip, trip_export

UTC = timezone.utc
CLAIM_AT = datetime(2026, 12, 3, 9, 40, tzinfo=timezone(timedelta(hours=1)))
CLAIM_KEYS = ("delay_min", "claim_paid_at")


def _trip(s, title, fingerprint, claim=False):
    t = Trip(title=title, origin_text="Amsterdam", destination_text="Zürich",
             date_from=date(2026, 12, 1), travelers=1, status="planning")
    it = Itinerary(fingerprint=fingerprint, mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC),
                   arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), duration_min=420, transfers=0, booked=True)
    it.booked_price, it.booked_currency = Decimal("150.00"), "EUR"
    it.booked_at = datetime(2026, 11, 5, 8, 30, tzinfo=UTC)
    if claim:
        it.delay_min, it.claim_paid_at = 75, CLAIM_AT.astimezone(UTC)
    it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                       to_name="Zürich", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC), depart_offset_min=0,
                       arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), arrive_offset_min=0))
    t.itineraries.append(it)
    s.add(t)
    s.commit()
    return t.id


def test_an_export_and_import_keep_the_delay_and_the_paid_claim(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Delayed", "fp-delay", claim=True)
        data = trip_export(load_trip(s, trip_id))
    assert data["itineraries"][0]["delay_min"] == 75
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.delay_min == 75
        assert it.claim_paid_at == CLAIM_AT.astimezone(UTC)
        assert it.claim_paid_at.utcoffset() == timedelta(0)


def test_an_export_from_before_the_change_imports_with_no_claim(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Booked", "fp-booked")
        data = trip_export(load_trip(s, trip_id))
    for key in CLAIM_KEYS:
        data["itineraries"][0].pop(key, None)
    with sessions() as s:
        r = import_trip(s, data)
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert (it.delay_min, it.claim_paid_at) == (None, None)
        assert (it.booked_price, it.booked_currency) == (Decimal("150.00"), "EUR")


def test_a_merge_into_a_trip_with_no_claim_keeps_the_delay_and_the_paid_claim(sessions):
    with sessions() as s:
        source = _trip(s, "Source", "fp-same", claim=True)
        target = _trip(s, "Target", "fp-same")
    with sessions() as s:
        merge_trips(s, source, target)
    with sessions() as s:
        it = load_trip(s, target).itineraries[0]
        assert it.delay_min == 75
        assert it.claim_paid_at == CLAIM_AT.astimezone(UTC)
