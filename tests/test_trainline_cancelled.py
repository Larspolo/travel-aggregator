"""A Trainline journey that thetrainline.com shows as cancelled marks its stored itinerary as cancelled by the operator
(#2773, the pattern of #2757)."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app import ingest
from app.ingest import fingerprint
from app.models import Itinerary, Trip
from app.parsers.trainline import TrainlineParser
from app.schemas import IngestIn

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com" / "search-london-edinburgh.json"
T1, T2 = (datetime(2026, 5, 1, h, tzinfo=UTC) for h in (8, 9))


def raw():
    return json.loads(FIX.read_text(encoding="utf-8"))


def search_of(r):
    return (r["response"] if "response" in r else r)["data"]["journeySearch"]


def journey_at(r, hhmm):
    """The journey whose first leg departs at `hhmm` (local time of the payload)."""
    s = search_of(r)
    for j in s["journeys"].values():
        if s["legs"][j["legs"][0]]["departAt"][11:16] == hhmm:
            return j
    raise AssertionError(f"no journey at {hhmm}")


def leg_at(r, hhmm):
    """The leg (of any journey, also a second leg) that departs at `hhmm`."""
    s = search_of(r)
    legs = [leg for leg in s["legs"].values() if leg["departAt"][11:16] == hhmm]
    assert len(legs) == 1, hhmm
    return legs[0]


def cancel_leg(r, hhmm, flag=True):
    """A copy of the payload in which the leg that departs at `hhmm` has `realTime.isCancelled` = `flag`."""
    c = copy.deepcopy(r)
    leg = leg_at(c, hhmm)
    leg["realTime"] = {"isCancelled": flag}
    return c


def test_a_cancelled_leg_gives_a_cancelled_connection_and_no_offer_or_error():
    r = TrainlineParser().parse(cancel_leg(raw(), "10:03"))
    assert r.errors == []
    assert len(r.cancelled) == 1
    assert len(r.cancelled[0]) == 1
    assert r.cancelled[0][0].depart_at.strftime("%H:%M") == "10:03"
    j = journey_at(raw(), "10:03")
    assert all(o.external_id != j["id"] for o in r.offers)


def test_a_cancelled_second_leg_cancels_the_whole_connection():
    r = TrainlineParser().parse(cancel_leg(raw(), "12:36"))
    assert r.errors == []
    assert len(r.cancelled) == 1
    assert [x.depart_at.strftime("%H:%M") for x in r.cancelled[0]] == ["10:33", "12:36"]
    j = journey_at(raw(), "10:33")
    assert all(o.external_id != j["id"] for o in r.offers)


def test_the_unchanged_fixture_gives_no_cancelled_connection():
    r = TrainlineParser().parse(raw())
    assert r.cancelled == []


def test_a_cancelled_journey_with_no_fare_is_cancelled_not_an_error():
    c = cancel_leg(raw(), "10:03")
    journey_at(c, "10:03")["sections"] = []
    r = TrainlineParser().parse(c)
    assert r.errors == []
    assert len(r.cancelled) == 1
    assert r.cancelled[0][0].depart_at.strftime("%H:%M") == "10:03"
    assert all(o.external_id != journey_at(raw(), "10:03")["id"] for o in r.offers)


def test_a_missing_realtime_is_not_cancelled():
    c = raw()
    del leg_at(c, "10:03")["realTime"]
    r = TrainlineParser().parse(c)
    assert r.cancelled == []


def test_an_ingest_marks_the_cancelled_itinerary(sessions):
    with sessions() as s:
        t = Trip(title="London – Edinburgh")
        s.add(t)
        s.commit()
        tid = t.id
        ingest.store(s, IngestIn(trip_id=tid, source="thetrainline.com", captured_at=T1, raw=raw()))
        ingest.store(s, IngestIn(trip_id=tid, source="thetrainline.com", captured_at=T2,
                                 raw=cancel_leg(raw(), "10:03")))
        s.expire_all()
        cancelled_legs = TrainlineParser().parse(cancel_leg(raw(), "10:03")).cancelled[0]
        target = s.scalar(select(Itinerary).where(Itinerary.trip_id == tid,
                                                  Itinerary.fingerprint == fingerprint(cancelled_legs)))
        assert target is not None
        assert target.operator_cancelled_at is not None
        assert target.operator_cancelled_at.replace(tzinfo=UTC) == T2
        others = s.scalars(select(Itinerary).where(Itinerary.trip_id == tid, Itinerary.id != target.id)).all()
        assert others and all(it.operator_cancelled_at is None for it in others)
