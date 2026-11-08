"""Move the offers of a capture to another trip (#579, epic #578): app/ingest.py move_capture()."""

import gzip
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import ingest
from app.models import Capture, Fare, FarePrice, Itinerary, Trip
from app.parsers import ParseResult
from app.schemas import IngestIn, OfferIn

BAHN = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"


def _offer(hour, price, to="Zürich"):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Flex",
            "legs": [{"mode": "train", "carrier": "DB", "service_no": f"ICE {hour}", "from_name": "Amsterdam",
                      "to_name": to, "depart_at": f"2026-12-01T{hour:02}:00:00+01:00",
                      "arrive_at": f"2026-12-01T{hour + 3:02}:00:00+01:00"}]}


class _Stub:
    """A parser whose raw is {"offers": [...]}: each test sets the offers of its captures."""
    source, version = "stub", "1"

    def parse(self, raw):
        if raw == "bad":
            raise ValueError("bad raw")
        return ParseResult(offers=[OfferIn.model_validate(o) for o in raw["offers"]])


@pytest.fixture
def stub(monkeypatch):
    real = ingest.get_parser
    monkeypatch.setattr(ingest, "get_parser", lambda source: _Stub() if source == "stub" else real(source))


def _trip(s, title, origin="Amsterdam", destination="Zürich"):
    trip = Trip(title=title, origin_text=origin, destination_text=destination)
    s.add(trip)
    s.commit()
    return trip.id


def _capture(s, trip_id, offers, day=1, raw=None, source="stub"):
    body = IngestIn.model_validate({"trip_id": trip_id, "source": source,
                                    "captured_at": datetime(2026, 11, day, 10, tzinfo=UTC),
                                    "raw": {"offers": offers} if raw is None else raw})
    ingest.store(s, body)
    return s.scalars(select(Capture).order_by(Capture.id.desc())).first()


def _offers(s, trip_id):
    """{departure hour: [(price, capture id) of each price row]} of the trip."""
    out = {}
    for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)):
        rows = [(p.price, p.capture_id) for f in it.fares for p in sorted(f.prices, key=lambda p: p.id)]
        out[it.depart_at.astimezone(UTC).hour + 1] = rows
    return out


def test_two_offers_go_to_the_target_and_leave_the_old_trip(sessions, stub):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        cap = _capture(s, a, [_offer(8, "10.50"), _offer(9, "20.00")])
        counts = ingest.move_capture(s, cap, b)
        assert counts == {"created": 2, "updated": 0, "unchanged": 0, "rejected": 0, "unreadable": None,
                          "removed": 2}
    with sessions() as s:
        assert _offers(s, a) == {}
        assert _offers(s, b) == {8: [(Decimal("10.50"), cap.id)], 9: [(Decimal("20.00"), cap.id)]}
        assert s.get(Capture, cap.id).trip_id == b
        assert s.scalar(select(func.count()).select_from(Fare)) == 2


def test_an_offer_of_another_capture_stays_with_only_its_price(sessions, stub):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        first = _capture(s, a, [_offer(8, "10.50"), _offer(9, "20.00")], day=1)
        second = _capture(s, a, [_offer(9, "25.00")], day=2)
        ingest.move_capture(s, first, b)
    with sessions() as s:
        assert _offers(s, a) == {9: [(Decimal("25.00"), second.id)]}
        fare = s.scalars(select(Fare).join(Fare.itinerary).where(Itinerary.trip_id == a)).one()
        assert fare.latest_price == Decimal("25.00") and fare.latest_captured_at == datetime(2026, 11, 2, 10, tzinfo=UTC)
        assert _offers(s, b) == {8: [(Decimal("10.50"), first.id)], 9: [(Decimal("20.00"), first.id)]}


def test_an_older_price_of_another_capture_becomes_the_latest_price(sessions, stub):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        _capture(s, a, [_offer(8, "30.00")], day=1)
        later = _capture(s, a, [_offer(8, "12.00")], day=2)
        ingest.move_capture(s, later, b)
    with sessions() as s:
        fare = s.scalars(select(Fare).join(Fare.itinerary).where(Itinerary.trip_id == a)).one()
        assert (fare.latest_price, fare.latest_captured_at) == (Decimal("30.00"), datetime(2026, 11, 1, 10, tzinfo=UTC))


def test_a_known_journey_of_the_target_keeps_its_pin_and_note(sessions, stub):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        _capture(s, b, [_offer(8, "10.50")], day=1)
        known = s.scalars(select(Itinerary).where(Itinerary.trip_id == b)).one()
        known.pinned, known.note = True, "take this one"
        s.commit()
        cap = _capture(s, a, [_offer(8, "9.00"), _offer(9, "20.00")], day=2)
        counts = ingest.move_capture(s, cap, b)
        assert (counts["created"], counts["updated"]) == (1, 1)
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == b).order_by(Itinerary.depart_at)).all()
        assert len(its) == 2 and its[0].id == known.id
        assert (its[0].pinned, its[0].note) == (True, "take this one")
        assert its[0].fares[0].latest_price == Decimal("9.00")


def test_the_marks_of_a_deleted_journey_go_to_the_target(sessions, stub):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        cap = _capture(s, a, [_offer(8, "10.50")])
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == a)).one()
        it.pinned, it.booked, it.note = True, True, "booked by phone"
        s.commit()
        ingest.move_capture(s, cap, b)
    with sessions() as s:
        moved = s.scalars(select(Itinerary).where(Itinerary.trip_id == b)).one()
        assert (moved.pinned, moved.booked, moved.hidden, moved.note) == (True, True, False, "booked by phone")


def test_the_trip_warning_is_computed_again_against_the_target(sessions, stub):
    with sessions() as s:
        wrong = _trip(s, "Lisbon", destination="Lisbon")
        right = _trip(s, "Zürich")
        cap = _capture(s, wrong, [_offer(8, "10.50")])
        assert cap.mismatch == "places"
        ingest.move_capture(s, cap, right)
    with sessions() as s:
        assert s.get(Capture, cap.id).mismatch is None


def test_a_real_bahn_capture_moves_all_its_offers(sessions):
    with sessions() as s:
        a = _trip(s, "A", "Köln", "Berlin")
        b = _trip(s, "B", "Köln", "München")
        cap = _capture(s, a, None, raw=json.loads(BAHN.read_text()), source="bahn.de")
        before = s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == a))
        assert before > 0 and cap.mismatch == "places"
        counts = ingest.move_capture(s, cap, b)
        assert counts["created"] == before and counts["removed"] == before
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == a)) == 0
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == b)) == before
        assert s.get(Capture, cap.id).mismatch is None


def _state(s):
    return (s.scalars(select(Capture.trip_id).order_by(Capture.id)).all(),
            s.scalars(select(Itinerary.trip_id).order_by(Itinerary.id)).all(),
            s.scalar(select(func.count()).select_from(FarePrice)))


def test_no_raw_gives_none_and_changes_nothing(sessions):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        ingest.store(s, IngestIn.model_validate({"trip_id": a, "source": "manual", "offers": [_offer(8, "10.50")],
                                                 "captured_at": datetime(2026, 11, 1, 10, tzinfo=UTC)}))
        cap = s.scalars(select(Capture)).one()
        before = _state(s)
        assert ingest.move_capture(s, cap, b) is None
        assert _state(s) == before


@pytest.mark.parametrize("target", ["same", "missing"])
def test_the_same_trip_or_a_missing_trip_raises_and_changes_nothing(sessions, stub, target):
    with sessions() as s:
        a = _trip(s, "A")
        cap = _capture(s, a, [_offer(8, "10.50")])
        before = _state(s)
        with pytest.raises(ValueError):
            ingest.move_capture(s, cap, a if target == "same" else a + 1000)
        assert _state(s) == before


def test_an_unreadable_raw_gives_the_reason_and_changes_nothing(sessions, stub):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        cap = _capture(s, a, [_offer(8, "10.50")])
        cap.raw_gz = gzip.compress(b'"bad"')
        s.commit()
        before = _state(s)
        assert ingest.move_capture(s, cap, b) == {"unreadable": "bad raw"}
        assert _state(s) == before


def test_a_failure_in_the_target_rolls_back_the_whole_move(sessions, stub, monkeypatch):
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        cap = _capture(s, a, [_offer(8, "10.50"), _offer(9, "20.00")])
        before = _state(s)
        calls = []
        real = ingest._upsert_one

        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("database gone")
            return real(*args, **kwargs)

        monkeypatch.setattr(ingest, "_upsert_one", fail_second)
        with pytest.raises(RuntimeError):
            ingest.move_capture(s, cap, b)
        assert _state(s) == before
        assert len(_offers(s, a)) == 2
