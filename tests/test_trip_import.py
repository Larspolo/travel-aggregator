"""The import of a trip from its JSON export (#776)."""

import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ingest import fingerprint
from app.models import Fare, FarePrice, Itinerary, Leg, Trip
from app.schemas import LegIn
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export

UTC = timezone.utc


def _itinerary(depart, arrive, offset, service, **kw):
    leg = Leg(seq=1, mode="train", carrier="DB", service_no=service, from_name="Amsterdam", to_name="Zürich",
              depart_at=depart, depart_offset_min=offset, arrive_at=arrive, arrive_offset_min=offset)
    tz = timezone(timedelta(minutes=offset))
    fp = fingerprint([LegIn(mode="train", service_no=service, from_name="A", to_name="B",
                            depart_at=depart.astimezone(tz), arrive_at=arrive.astimezone(tz))])
    it = Itinerary(fingerprint=fp, mode_summary="train", depart_at=depart, arrive_at=arrive,
                   duration_min=int((arrive - depart).total_seconds() // 60), transfers=0, **kw)
    it.legs.append(leg)
    return it


def _fare(name, *prices):
    last = prices[-1]
    fare = Fare(source="bahn", fare_name=name, travel_class="standard", flexibility="none",
                booking_url="https://example.com/b", latest_price=Decimal(last[1]), currency="EUR",
                latest_captured_at=last[0])
    fare.prices += [FarePrice(price=Decimal(p), currency="EUR", captured_at=at) for at, p in prices]
    return fare


@pytest.fixture
def export(sessions):
    d3, d4 = datetime(2026, 11, 3, tzinfo=UTC), datetime(2026, 11, 4, tzinfo=UTC)
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 date_from=date(2026, 12, 1), travelers=2, status="planning", notes="ski")
        a = _itinerary(datetime(2026, 12, 1, 8, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC), 60, "ICE 105",
                       pinned=True, note="best")
        a.fares += [_fare("Sparpreis", (d3, "89.90"), (d4, "79.90")), _fare("Flexpreis", (d3, "150.00"))]
        b = _itinerary(datetime(2026, 12, 1, 10, tzinfo=UTC), datetime(2026, 12, 1, 17, tzinfo=UTC), 0, "ICE 107",
                       hidden=True, booked=True)
        b.fares.append(_fare("Sparpreis", (d4, "99.00")))
        t.itineraries += [a, b]
        s.add(t)
        s.commit()
        return trip_export(load_trip(s, t.id))


def _strip(data):
    data = copy.deepcopy(data)
    data.pop("exported_at")
    data["trip"].pop("id")
    for it in data["itineraries"]:
        it.pop("id")
    return data


def _counts(s):
    return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Trip, Itinerary, Fare, FarePrice))


def test_an_import_gives_the_same_export(sessions, export):
    with sessions() as s:
        r = import_trip(s, export)
        s.commit()
        assert (r.itineraries_added, r.fares_added, r.prices_added) == (2, 3, 4)
        again = trip_export(load_trip(s, r.trip_id))
    assert again["trip"]["id"] != export["trip"]["id"]
    assert _strip(again) == _strip(export)


def test_a_second_import_adds_no_row(sessions, export):
    with sessions() as s:
        r = import_trip(s, export)
        s.commit()
        before = _counts(s)
        r2 = import_trip(s, export, trip_id=r.trip_id)
        s.commit()
        assert _counts(s) == before
    assert (r2.itineraries_added, r2.fares_added, r2.prices_added) == (0, 0, 0)
    assert (r2.itineraries_unchanged, r2.fares_unchanged, r2.prices_unchanged) == (2, 3, 4)


def test_an_older_export_keeps_the_newer_latest_price(sessions, export):
    old = copy.deepcopy(export)
    fare = old["itineraries"][0]["fares"][0]
    fare["prices"] = fare["prices"][:1]
    fare["latest_price"], fare["latest_captured_at"] = fare["prices"][0]["price"], fare["prices"][0]["captured_at"]
    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        import_trip(s, old, trip_id=trip_id)
        s.commit()
        data = trip_export(load_trip(s, trip_id))
    assert data["itineraries"][0]["fares"][0]["latest_price"] == "79.90"


def _bad_format(d):
    d["format"] = "other"


def _bad_version(d):
    d["version"] = 2


def _bad_price(d):
    d["itineraries"][1]["fares"][0]["prices"][0]["price"] = "a lot"


def _naive_time(d):
    d["itineraries"][1]["legs"][0]["depart_at"] = "2026-12-01T10:00:00"


@pytest.mark.parametrize("change, text", [(_bad_format, "not a trip export"),
                                          (_bad_version, "export version 2 is not known"),
                                          (_bad_price, "not valid"), (_naive_time, "not valid")])
def test_a_bad_export_gives_a_value_error_and_no_row(sessions, export, change, text):
    bad = copy.deepcopy(export)
    change(bad)
    with sessions() as s:
        before = _counts(s)
        with pytest.raises(ValueError, match=text):
            import_trip(s, bad)
        s.rollback()
        assert _counts(s) == before
