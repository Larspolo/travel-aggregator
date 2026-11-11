"""The search status of each source for one trip (#967): the newest capture of the trip, or none."""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Capture
from app.parsers import all_sources
from app.sales_open import sales_open_on
from app.search_links import links_by_source
from app.sourcehealth import failed_clause


def trip_coverage(session: Session, trip, today: date | None = None, horizon: dict[str, int] | None = None) -> list[dict]:
    """One entry per parser source, in source order, from one query (no query per source).

    Each entry: source, name, url (the search link or None), captured_at, offer_count (None: not searched yet) and failed (the newest capture failed, #968) and
    sales_open_on (#2254: the first sales date when it is today or later, else None; on that date the source shows no link)."""
    today = today or datetime.now(timezone.utc).date()
    days = horizon or {}  # the caller reads `app.sales_open.horizons()` once
    query = (select(Capture.source, Capture.captured_at, Capture.offer_count, failed_clause().label("failed"))
             .where(Capture.trip_id == trip.id).distinct(Capture.source)
             .order_by(Capture.source, Capture.captured_at.desc(), Capture.id.desc()))
    newest = {r.source: r for r in session.execute(query)}
    links = links_by_source(trip)
    entries = []
    for source in all_sources() + [k for k in links if k not in all_sources()]:  # a link with no parser: last
        name, url = links.get(source, (source, None))
        row = newest.get(source)
        opens = sales_open_on(trip.date_from, days.get(source)) if trip.date_from else None
        opens = opens if opens is not None and opens >= today else None
        entries.append({"source": source, "name": name, "url": url,
                        "captured_at": row.captured_at if row else None,
                        "offer_count": row.offer_count if row else None,
                        "failed": bool(row.failed) if row else False,
                        "sales_open_on": opens})
    return entries
