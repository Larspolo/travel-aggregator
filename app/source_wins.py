"""The sources that give the best offers (#1940): for each source, the trips of the last 365 days in which it has a
capture and the trips in which the best offer by the default profile has its main fare from it. Stores nothing."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Capture, Trip
from app.profiles import default_weights


@dataclass(frozen=True)
class SourceWins:
    source: str
    best: int
    trips: int


def source_wins(session: Session, now: datetime) -> list[SourceWins]:
    """One row for each source with a capture in the 365 days before `now`; `best` high first, then the source name.
    The best offer of a trip is the one of the default profile (not the profile of the trip), at its newest capture."""
    from app.web.pages import best_for_weights  # the web module imports much: import it only when needed

    rows = session.execute(select(Capture.trip_id, Capture.source)
                           .where(Capture.captured_at >= now - timedelta(days=365)).distinct()).all()
    trips = Counter(source for _, source in rows)
    weights, best = default_weights(session), Counter()
    for trip_id in sorted({trip_id for trip_id, _ in rows}):
        at = session.scalar(select(func.max(Capture.captured_at)).where(Capture.trip_id == trip_id))
        row = best_for_weights(session, session.get(Trip, trip_id), weights, at)
        if row is not None:
            best[row[1].source] += 1
    return sorted((SourceWins(s, best[s], n) for s, n in trips.items()), key=lambda w: (-w.best, w.source))
