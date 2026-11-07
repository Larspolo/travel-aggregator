"""The journey key as the fingerprint of an itinerary, and one itinerary per journey (#484, epic #481).

Revision ID: 0014
Revises: 0013

This migration changes data. The upgrade gives each itinerary the fingerprint of its journey key (the mode and the
normalized service number of each leg, the UTC first departure and last arrival; no carrier, no times between). When
two itineraries of one trip get the same value, it keeps the oldest one (lowest id) and moves to it the fares of the
others with their price rows; it then deletes the others. Two fares of one source and fare name become one fare:
the newest values and all price rows. `pinned` and `booked` are true when one of them is, `hidden` only when all are,
and the notes are joined with a new line. The kept itinerary gets the real legs of one of them (not the legs of an
NS International offer with a change station).
The downgrade gives the kept itineraries the old fingerprint again (mode, carrier, service number and times of each
leg). The merged itineraries do not come back: their fares and prices stay on the kept itinerary.
The functions of the fingerprint are copies here, so that a later change in app/ingest.py does not change this file.
"""

import hashlib
from datetime import UTC

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None
changes_data = True

CHANGE_STATION = "change station"  # app/parsers/ns.py: a leg between the journey start and end


def _new_fingerprint(legs) -> str:
    parts = [f"{leg.mode}|{''.join((leg.service_no or '').split()).upper()}" for leg in legs]
    parts += [legs[0].depart_at.astimezone(UTC).isoformat(), legs[-1].arrive_at.astimezone(UTC).isoformat()]
    return hashlib.sha256(("journey\n" + "\n".join(parts)).encode()).hexdigest()


def _old_fingerprint(legs) -> str:
    parts = [f"{leg.mode}|{leg.carrier or ''}|{leg.service_no or ''}|{leg.depart_at.astimezone(UTC).isoformat()}|"
             f"{leg.arrive_at.astimezone(UTC).isoformat()}" for leg in legs]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _legs_by_itinerary(conn) -> dict[int, list]:
    rows = conn.execute(sa.text("SELECT itinerary_id, mode, carrier, service_no, from_name, to_name, depart_at, "
                                "arrive_at FROM legs ORDER BY itinerary_id, seq")).all()
    legs: dict[int, list] = {}
    for row in rows:
        legs.setdefault(row.itinerary_id, []).append(row)
    return legs


def _merge_fares(conn, keep_id: int) -> None:
    """One fare per (source, fare name) of the kept itinerary: the newest values, all price rows."""
    fares = conn.execute(sa.text("SELECT id, source, fare_name, latest_captured_at FROM fares WHERE itinerary_id = :i "
                                 "ORDER BY latest_captured_at DESC, id DESC"), {"i": keep_id}).all()
    groups: dict[tuple, list] = {}
    for fare in fares:
        groups.setdefault((fare.source, fare.fare_name), []).append(fare)
    for newest, *older in groups.values():
        for fare in older:
            conn.execute(sa.text("UPDATE fare_prices SET fare_id = :n WHERE fare_id = :o"),
                         {"n": newest.id, "o": fare.id})
            conn.execute(sa.text("DELETE FROM fares WHERE id = :o"), {"o": fare.id})


def _merge(conn, ids: list[int], legs: dict[int, list]) -> None:
    keep, others = ids[0], ids[1:]
    rows = conn.execute(sa.text("SELECT id, pinned, booked, hidden, note, first_seen_at, last_seen_at "
                                "FROM itineraries WHERE id = ANY(:ids) ORDER BY id"), {"ids": ids}).all()
    notes = [r.note for r in rows if r.note and r.note.strip()]
    conn.execute(sa.text("UPDATE itineraries SET pinned = :p, booked = :b, hidden = :h, note = :n, "
                         "first_seen_at = :f, last_seen_at = :l WHERE id = :i"),
                 {"p": any(r.pinned for r in rows), "b": any(r.booked for r in rows),
                  "h": all(r.hidden for r in rows), "n": "\n".join(notes) or None,
                  "f": min(r.first_seen_at for r in rows), "l": max(r.last_seen_at for r in rows), "i": keep})
    conn.execute(sa.text("UPDATE fares SET itinerary_id = :k WHERE itinerary_id = ANY(:o)"), {"k": keep, "o": others})
    real = [i for i in ids if all(CHANGE_STATION not in (leg.from_name, leg.to_name) for leg in legs.get(i, []))]
    if real and real[0] != keep:
        conn.execute(sa.text("DELETE FROM legs WHERE itinerary_id = :k"), {"k": keep})
        conn.execute(sa.text("UPDATE legs SET itinerary_id = :k WHERE itinerary_id = :r"), {"k": keep, "r": real[0]})
    conn.execute(sa.text("DELETE FROM itineraries WHERE id = ANY(:o)"), {"o": others})  # their legs by cascade
    _merge_fares(conn, keep)


def _set_fingerprints(conn, function) -> None:
    for itinerary_id, legs in _legs_by_itinerary(conn).items():
        conn.execute(sa.text("UPDATE itineraries SET fingerprint = :f WHERE id = :i"),
                     {"f": function(legs), "i": itinerary_id})


def upgrade() -> None:
    conn = op.get_bind()
    legs = _legs_by_itinerary(conn)
    groups: dict[tuple, list[int]] = {}
    for row in conn.execute(sa.text("SELECT id, trip_id FROM itineraries ORDER BY id")).all():
        if row.id in legs:
            groups.setdefault((row.trip_id, _new_fingerprint(legs[row.id])), []).append(row.id)
    for ids in groups.values():
        if len(ids) > 1:
            _merge(conn, ids, legs)
    # The new values are distinct per trip now, and the "journey" prefix keeps them apart from the old values.
    _set_fingerprints(conn, _new_fingerprint)


def downgrade() -> None:
    # The old key has all parts of the new key, so distinct new values give distinct old values.
    _set_fingerprints(op.get_bind(), _old_fingerprint)
