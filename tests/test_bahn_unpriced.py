"""A bahn.de connection that shows "Preis ermitteln" (no price) is no rejected offer when another connection has a price (#2810)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app import ingest
from app.models import Trip
from app.parsers.bahn import BahnParser
from app.schemas import IngestIn

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"
T2 = datetime(2026, 5, 1, 9, tzinfo=UTC)


def raw():
    return json.loads(FIX.read_text(encoding="utf-8"))


def unpriced(r, index):
    """The payload with no price (no `reiseAngebote`, no `angebotsPreis`) for connection `index`."""
    conn = r["response"]["verbindungen"][index]
    conn.pop("reiseAngebote", None)
    conn.pop("angebotsPreis", None)
    return r


def test_a_connection_with_no_price_is_skipped_when_another_has_one():
    base = BahnParser().parse(raw())
    r = BahnParser().parse(unpriced(raw(), 0))
    tid = raw()["response"]["verbindungen"][0]["tripId"]
    assert r.errors == []
    assert [o for o in r.offers if o.external_id != tid] == [o for o in base.offers if o.external_id != tid]
    assert not any(o.external_id == tid for o in r.offers)


def test_no_connection_with_a_price_keeps_one_error_per_connection():
    r = raw()
    for i in range(len(r["response"]["verbindungen"])):
        unpriced(r, i)
    result = BahnParser().parse(r)
    conns = r["response"]["verbindungen"]
    assert result.offers == []
    assert len(result.errors) == len(conns) - len(result.cancelled)
    assert {e["reason"] for e in result.errors} == {"no price (angebotsPreis)"}


def trip(s):
    t = Trip(title="Köln – München")
    s.add(t)
    s.commit()
    return t.id


def test_the_capture_of_an_unpriced_connection_has_no_rejected_offer(sessions):
    with sessions() as s:
        tid = trip(s)
        answer = ingest.store(s, IngestIn(trip_id=tid, source="bahn.de", captured_at=T2, raw=unpriced(raw(), 0)))
        assert answer["rejected"] == 0
