"""Delete one capture with its price rows, day prices and the offers that only it gave (#2186, `capture:delete`).

This is a copy of the steps of `ingest._remove_from_old_trip()` (#579), not a shared helper: the delete keeps rows
that the move deletes (a booked, pinned or noted journey, a fare seen again at an unchanged price) and needs a dry
run for the confirm page. A shared helper with these flags would make `move_capture()` harder to read."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Capture, DayPrice, FarePrice


def _plan(session: Session, capture: Capture) -> dict:
    """What the delete does: the price rows to delete, the rows to keep with no capture, the fares and the
    itineraries to delete, and the day prices. Changes nothing."""
    rows = session.scalars(select(FarePrice).where(FarePrice.capture_id == capture.id)).all()
    fares = list({r.fare.id: r.fare for r in rows}.values())
    drop_rows, keep_rows, drop_fares = [], [], []
    for fare in fares:
        mine = [r for r in fare.prices if r.capture_id == capture.id]
        newest = max(fare.prices, key=lambda p: (p.captured_at, p.id))
        it = fare.itinerary
        protected = it.booked or it.pinned or bool(it.note)
        others = len(fare.prices) - len(mine)
        # an unchanged price adds no row: a later capture saw the price of the newest row (#1404)
        seen_later = newest.capture_id == capture.id and fare.latest_captured_at > newest.captured_at
        if seen_later or (others == 0 and protected):
            keep_rows.append(newest)
            drop_rows += [r for r in mine if r is not newest]
        else:
            drop_rows += mine
            if others == 0:
                drop_fares.append(fare)
    drop_ids = {f.id for f in drop_fares}
    itineraries = list({f.itinerary.id: f.itinerary for f in drop_fares}.values())
    drop_its = [it for it in itineraries if all(f.id in drop_ids for f in it.fares)]
    days = session.scalars(select(DayPrice).where(DayPrice.capture_id == capture.id)).all()
    return {"rows": drop_rows, "keep": keep_rows, "fares": drop_fares, "itineraries": drop_its, "days": days}


def _counts(plan: dict) -> dict:
    return {"prices": len(plan["rows"]), "fares": len(plan["fares"]), "itineraries": len(plan["itineraries"]),
            "day_prices": len(plan["days"])}


def delete_counts(session: Session, capture: Capture) -> dict:
    """The counts for the confirm page: `prices`, `fares`, `itineraries`, `day_prices`. Changes nothing."""
    return _counts(_plan(session, capture))


def delete_capture(session: Session, capture: Capture) -> dict:
    """Delete the capture and what only it gave; a kept fare gets the price of its newest row again. Returns the
    counts of what it deleted. The caller commits."""
    plan = _plan(session, capture)
    touched = list({r.fare.id: r.fare for r in plan["rows"] + plan["keep"]}.values())
    for r in plan["keep"]:
        r.capture_id = None
    for r in plan["rows"]:
        r.fare.prices.remove(r)  # delete-orphan: the row is deleted at the flush
    gone = {f.id for f in plan["fares"]}
    for fare in touched:
        if fare.id in gone:
            fare.itinerary.fares.remove(fare)
        elif fare.prices and not any(r.fare is fare for r in plan["keep"]):
            newest = max(fare.prices, key=lambda p: (p.captured_at, p.id))
            fare.latest_price, fare.currency, fare.latest_captured_at = newest.price, newest.currency, newest.captured_at
    for it in plan["itineraries"]:
        session.delete(it)  # #2144: the database deletes the rows joined into it
    for d in plan["days"]:
        session.delete(d)
    session.flush()
    session.delete(capture)
    session.flush()
    return _counts(plan)
