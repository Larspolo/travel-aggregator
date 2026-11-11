"""The booking code of a booked journey in the JSON export, the import and the merge (#1716, #1718)."""

import copy
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models import Itinerary, Leg, Trip
from app.trip_import import import_trip
from app.trip_merge import merge_trips
from app.web.export import load_trip, trip_export

UTC = timezone.utc
CODE = "K7Q2XP"


def _trip(s, title, fingerprint, code=None):
    t = Trip(title=title, origin_text="Amsterdam", destination_text="Zürich",
             date_from=date(2026, 12, 1), travelers=1, status="planning")
    it = Itinerary(fingerprint=fingerprint, mode_summary="train", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC),
                   arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), duration_min=420, transfers=0, booked=True)
    it.booked_price, it.booked_currency = Decimal("150.00"), "EUR"
    it.booked_at = datetime(2026, 11, 5, 8, 30, tzinfo=UTC)
    it.booking_code = code
    it.legs.append(Leg(seq=1, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam",
                       to_name="Zürich", depart_at=datetime(2026, 12, 1, 8, tzinfo=UTC), depart_offset_min=0,
                       arrive_at=datetime(2026, 12, 1, 15, tzinfo=UTC), arrive_offset_min=0))
    t.itineraries.append(it)
    s.add(t)
    s.commit()
    return t.id


def test_an_export_has_the_booking_code(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Coded", "fp-code", code=CODE)
        data = trip_export(load_trip(s, trip_id))
    assert data["itineraries"][0]["booking_code"] == CODE


def test_an_import_of_the_export_keeps_the_booking_code(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Coded", "fp-code", code=CODE)
        data = trip_export(load_trip(s, trip_id))
    with sessions() as s:
        r = import_trip(s, copy.deepcopy(data))
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.booking_code == CODE


def test_an_import_with_a_41_character_code_is_rejected_and_adds_no_row(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Coded", "fp-code", code=CODE)
        data = trip_export(load_trip(s, trip_id))
    bad = copy.deepcopy(data)
    bad["itineraries"][0]["booking_code"] = "A" * 41
    with sessions() as s:
        with pytest.raises(ValueError, match="not valid"):
            import_trip(s, bad)
        s.rollback()
    with sessions() as s:
        assert len(s.query(Trip).all()) == 1


def test_an_export_from_before_the_change_imports_with_no_code(sessions):
    with sessions() as s:
        trip_id = _trip(s, "Old", "fp-old", code=CODE)
        data = trip_export(load_trip(s, trip_id))
    data["itineraries"][0].pop("booking_code", None)
    with sessions() as s:
        r = import_trip(s, data)
        s.commit()
        it = load_trip(s, r.trip_id).itineraries[0]
        assert it.booking_code is None


def test_a_merge_into_a_trip_with_no_code_keeps_the_booking_code(sessions):
    with sessions() as s:
        source = _trip(s, "Source", "fp-same", code=CODE)
        target = _trip(s, "Target", "fp-same")
    with sessions() as s:
        merge_trips(s, source, target)
    with sessions() as s:
        it = load_trip(s, target).itineraries[0]
        assert it.booking_code == CODE
