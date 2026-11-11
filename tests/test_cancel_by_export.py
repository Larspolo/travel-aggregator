"""The cancel time of a booked journey in the JSON export, the import, the merge and the join (#2313)."""

import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models import Itinerary, Leg, Trip
from app.same_journey import join
from app.trip_import import import_trip
from app.trip_merge import merge_trips
from app.web.export import load_trip, trip_export

UTC = timezone.utc
CET = timezone(timedelta(hours=1))
CANCEL_UTC = datetime(2026, 12, 18, 17, 0, tzinfo=UTC)  # 18:00 at +01:00


def _trip(s, title, fingerprint, cancel=None, booked=True):
    t = Trip(title=title, origin_text="Amsterdam", destination_text="Zürich",
             date_from=date(2026, 12, 1), travelers=1, status="planning")
    it = Itinerary(fingerprint=fingerprint, mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC),
                   arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), duration_min=420, transfers=0, booked=booked)
    if booked:
        it.booked_price, it.booked_currency = Decimal("150.00"), "EUR"
        it.booked_at = datetime(2026, 11, 5, 8, 30, tzinfo=UTC)
    if cancel is not None:
        it.cancel_by, it.cancel_by_offset_min = cancel, 60
    it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                       to_name="Zürich", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC), depart_offset_min=0,
                       arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), arrive_offset_min=0))
    t.itineraries.append(it)
    s.add(t)
    s.commit()
    return t.id


def test_an_export_has_the_cancel_time_with_its_offset(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Cancel", "fp-cancel", cancel=CANCEL_UTC)
        data = trip_export(load_trip(s, trip_id))
    row = data["itineraries"][0]
    assert row["cancel_by"] == "2026-12-18T18:00:00+01:00"
    assert row["cancel_by_offset_min"] == 60


def test_an_export_and_import_keep_the_cancel_time(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Cancel", "fp-cancel", cancel=CANCEL_UTC)
        data = trip_export(load_trip(s, trip_id))
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.cancel_by == CANCEL_UTC
        assert it.cancel_by_offset_min == 60


def test_an_old_export_with_no_cancel_fields_imports_with_no_cancel_time(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Old", "fp-old", cancel=CANCEL_UTC)
        data = trip_export(load_trip(s, trip_id))
    data = copy.deepcopy(data)
    data["itineraries"][0].pop("cancel_by", None)
    data["itineraries"][0].pop("cancel_by_offset_min", None)
    with sessions() as s:
        r = import_trip(s, data)
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.cancel_by is None
        assert it.cancel_by_offset_min is None


def test_a_merge_into_a_trip_with_no_cancel_time_keeps_it(sessions):
    with sessions() as s:
        source = _trip(s, "Source", "fp-same", cancel=CANCEL_UTC)
        target = _trip(s, "Target", "fp-same")
    with sessions() as s:
        merge_trips(s, source, target)
    with sessions() as s:
        it = load_trip(s, target).itineraries[0]
        assert it.cancel_by == CANCEL_UTC
        assert it.cancel_by_offset_min == 60


def test_a_merge_keeps_the_cancel_time_of_the_target_when_it_has_one(sessions):
    later = CANCEL_UTC + timedelta(days=1)
    with sessions() as s:
        source = _trip(s, "Source", "fp-same", cancel=CANCEL_UTC)
        target = _trip(s, "Target", "fp-same", cancel=later)
    with sessions() as s:
        merge_trips(s, source, target)
    with sessions() as s:
        it = load_trip(s, target).itineraries[0]
        assert it.cancel_by == later


def test_a_join_gives_the_cancel_time_of_b_to_a_when_a_has_none(sessions):
    with sessions() as s:
        t = Trip(title="Join", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 1), travelers=1, status="planning")
        for fp, cancel in (("fp-a", None), ("fp-b", CANCEL_UTC)):
            it = Itinerary(fingerprint=fp, mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC),
                           arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), duration_min=420, transfers=0)
            it.cancel_by, it.cancel_by_offset_min = cancel, (60 if cancel else None)
            it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                               to_name="Zürich", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC), depart_offset_min=0,
                               arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), arrive_offset_min=0))
            t.itineraries.append(it)
        s.add(t)
        s.commit()
        trip_id = t.id
    with sessions() as s:
        a = s.query(Itinerary).filter_by(trip_id=trip_id, fingerprint="fp-a").one()
        b = s.query(Itinerary).filter_by(trip_id=trip_id, fingerprint="fp-b").one()
        join(s, a, b)
        s.commit()
    with sessions() as s:
        a = s.query(Itinerary).filter_by(trip_id=trip_id, fingerprint="fp-a").one()
        assert a.cancel_by == CANCEL_UTC
        assert a.cancel_by_offset_min == 60
