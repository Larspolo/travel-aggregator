"""An sbb.ch trip that the site shows as cancelled marks its stored itinerary as cancelled by the operator (#2757)."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app import ingest
from app.models import Itinerary, Trip
from app.parsers.sbb import SbbParser
from app.schemas import IngestIn

FIX = Path(__file__).parent / "fixtures" / "sbb.ch" / "search-basel-zuerich.json"
T1, T2, T3 = (datetime(2026, 5, 1, h, tzinfo=UTC) for h in (8, 9, 10))


def raw():
    return json.loads(FIX.read_text(encoding="utf-8"))


def with_status(**flags):
    r = copy.deepcopy(raw())
    r["response"]["data"]["trips"]["trips"][0]["summary"]["tripStatus"].update(flags)
    return r


def names(conn):
    return [(x.service_no, x.from_name, x.to_name) for x in conn]


def trip(s):
    t = Trip(title="Basel – Zürich")
    s.add(t)
    s.commit()
    return t.id


def test_a_cancelled_trip_is_cancelled_and_no_offer_or_error():
    r = SbbParser().parse(with_status(cancelled=True))
    assert r.errors == []
    assert len(r.cancelled) == 1
    assert names(r.cancelled[0]) == [("IC 763", "Basel SBB", "Zürich HB")]
    assert len(r.offers) == 8
    assert all(o.legs[0].service_no != "IC 763" for o in r.offers)


def test_a_partly_cancelled_trip_gives_the_same():
    a = SbbParser().parse(with_status(cancelled=True))
    b = SbbParser().parse(with_status(partiallyCancelled=True))
    assert names(a.cancelled[0]) == names(b.cancelled[0])
    assert b.errors == []
    assert len(b.cancelled) == 1


def test_the_unchanged_fixture_gives_no_cancelled_connection():
    r = SbbParser().parse(raw())
    assert r.cancelled == []


def test_a_cancelled_trip_with_no_price_is_cancelled_not_no_price():
    r = SbbParser().parse(with_status(cancelled=True))
    assert not any(e.get("reason") == "no price" for e in r.errors)
    assert len(r.cancelled) == 1


def test_a_missing_summary_is_not_cancelled():
    r = raw()
    del r["response"]["data"]["trips"]["trips"][0]["summary"]
    res = SbbParser().parse(r)
    assert res.cancelled == []


def test_an_ingest_marks_the_cancelled_itinerary_and_keeps_the_best_other(sessions):
    with sessions() as s:
        tid = trip(s)
        ingest.store(s, IngestIn(trip_id=tid, source="sbb.ch", captured_at=T1, raw=raw()))
        ingest.store(s, IngestIn(trip_id=tid, source="sbb.ch", captured_at=T2, raw=with_status(cancelled=True)))
        s.expire_all()
        marked = s.scalars(select(Itinerary).where(Itinerary.trip_id == tid,
                                                   Itinerary.operator_cancelled_at.is_not(None))).all()
        assert len(marked) == 1
        assert marked[0].operator_cancelled_at.replace(tzinfo=UTC) == T2
        others = s.scalars(select(Itinerary).where(Itinerary.trip_id == tid, Itinerary.id != marked[0].id)).all()
        assert others and all(it.operator_cancelled_at is None for it in others)
