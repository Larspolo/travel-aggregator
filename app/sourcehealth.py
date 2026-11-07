"""The status of each source (#724): the last good capture, its parser version and the failed captures after it."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Capture

WARN_FAILED = 2  # the trips list warns when this many captures failed after the last good one (#726)


def failed_clause():
    """A capture failed when the parser could not read it or rejected an offer (#349)."""
    return or_(Capture.unreadable.is_not(None), Capture.rejected_count > 0)


def _good_clause():
    """A capture is good when the parser read it and rejected no offer."""
    return and_(Capture.unreadable.is_(None), func.coalesce(Capture.rejected_count, 0) == 0,
                Capture.offer_count.is_not(None))


def source_health(session: Session) -> list[dict]:
    """One entry per source, in source order, from two queries (no query per capture)."""
    good = (select(Capture.source, Capture.captured_at, Capture.parser_version)
            .where(_good_clause()).distinct(Capture.source)
            .order_by(Capture.source, Capture.captured_at.desc(), Capture.id.desc())).subquery()
    query = (select(Capture.source, func.max(Capture.captured_at).label("last_at"),
                    func.max(good.c.captured_at).label("last_good_at"),
                    func.max(good.c.parser_version).label("parser_version"),
                    func.count(Capture.id).filter(failed_clause(), or_(good.c.captured_at.is_(None),
                                                                       Capture.captured_at > good.c.captured_at))
                    .label("failed_after"))
             .outerjoin(good, good.c.source == Capture.source)
             .group_by(Capture.source).order_by(Capture.source))
    return [{"source": r.source, "last_good_at": r.last_good_at, "parser_version": r.parser_version,
             "failed_after": r.failed_after, "last_at": r.last_at} for r in session.execute(query)]


def failing_sources(session: Session) -> list[dict]:
    """The sources whose newest WARN_FAILED or more captures failed, for the warning of the trips list (#726)."""
    return [h for h in source_health(session) if h["failed_after"] >= WARN_FAILED]
