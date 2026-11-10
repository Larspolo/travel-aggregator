"""The status of each source (#724): the last good capture, its parser version and the failed captures after it."""

from datetime import UTC, datetime
from urllib.parse import urlencode

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Capture, Setting, SilentPage

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
    newest = (select(Capture.source, Capture.parser_version)
              .distinct(Capture.source)
              .order_by(Capture.source, Capture.captured_at.desc(), Capture.id.desc())).subquery()
    query = (select(Capture.source, func.max(Capture.captured_at).label("last_at"),
                    func.max(newest.c.parser_version).label("script_version"),
                    func.max(good.c.captured_at).label("last_good_at"),
                    func.max(good.c.parser_version).label("parser_version"),
                    func.count(Capture.id).filter(failed_clause(), or_(good.c.captured_at.is_(None),
                                                                       Capture.captured_at > good.c.captured_at))
                    .label("failed_after"))
             .outerjoin(good, good.c.source == Capture.source)
             .outerjoin(newest, newest.c.source == Capture.source)
             .group_by(Capture.source).order_by(Capture.source))
    rows = [{"source": r.source, "last_good_at": r.last_good_at, "parser_version": r.parser_version,
             "failed_after": r.failed_after, "last_at": r.last_at, "script_version": r.script_version,
             "silent_after": 0, "silent_at": None}
            for r in session.execute(query)]
    _add_silent(session, rows)
    _add_old_parsed(session, rows)
    return rows


def old_parsed_clause(source: str, version: str):
    """A good capture with raw data that an older (or unknown) parser version read (#1990)."""
    return and_(Capture.source == source, Capture.unreadable.is_(None),
                func.coalesce(Capture.rejected_count, 0) == 0, Capture.raw_gz.is_not(None),
                or_(Capture.parsed_with.is_(None), Capture.parsed_with != version))


def _add_old_parsed(session: Session, rows: list[dict]) -> None:
    from app.parsers import get_parser
    for row in rows:
        parser = get_parser(row["source"])
        row["old_parsed"], row["current_version"] = 0, None
        if parser is None:
            continue
        row["current_version"] = parser.version
        row["old_parsed"] = session.scalar(
            select(func.count(Capture.id)).where(old_parsed_clause(row["source"], parser.version)))


def _add_silent(session: Session, rows: list[dict]) -> None:
    """The silent pages (#1755) after the last good capture of each source: the count and the newest time."""
    by_source = {r["source"]: r for r in rows}
    for page in session.scalars(select(SilentPage).order_by(SilentPage.seen_at)):
        r = by_source.get(page.source)
        if r is None:
            r = by_source[page.source] = {"source": page.source, "last_good_at": None, "parser_version": None,
                                          "failed_after": 0, "last_at": None, "script_version": None,
                                          "silent_after": 0, "silent_at": None}
            rows.append(r)
        if r["last_good_at"] is None or page.seen_at > r["last_good_at"]:
            r["silent_after"] += 1
            r["silent_at"] = page.seen_at
    rows.sort(key=lambda r: r["source"])


def add_old_script(health: list[dict]) -> list[dict]:
    """Set "served_version" when the newest capture came from an older userscript than the served one (#1495).

    A capture with no parser_version (an upload, a manual offer) or a source with no served script gives no warning.
    """
    from app.web.userscripts import _weight, served_versions

    served = served_versions()
    for h in health:
        version, current = h.get("script_version"), served.get(h["source"])
        h["served_version"] = current if version and current and _weight(version) < _weight(current) else None
    return health


def failing_sources(session: Session) -> list[dict]:
    """The sources whose newest WARN_FAILED or more captures failed, for the warning of the trips list (#726)."""
    return [h for h in source_health(session) if h["failed_after"] >= WARN_FAILED]


ALERT_PREFIX = "source_alert:"  # #1172: one row per source that has an open "failed" message


def source_alert_messages(session: Session, base_url: str) -> list:
    """A message "<source>: the last N captures failed" once per failure, and "<source> works again" after a good capture.

    The caller commits and delivers. The channel `none` gives no message and stores no row (#1172).
    """
    from app.notify import SOURCE_ALERT_KEY, alert_messages, setting

    if setting(session, SOURCE_ALERT_KEY, "1") == "0":  # #1174: the owner turned the messages off
        return []
    now = datetime.now(UTC).isoformat()
    base = base_url.rstrip("/")
    health = {h["source"]: h for h in source_health(session)}
    msgs = []
    for h in failing_sources(session):
        source = h["source"]
        key = f"{ALERT_PREFIX}{source}"
        if session.get(Setting, key) is not None:
            continue
        link = f"{base}/captures?{urlencode({'failed': 1, 'source': source})}"
        n = h["failed_after"]
        title = f"{source}: the last {n} capture{'' if n == 1 else 's'} failed"
        new = alert_messages(session, title, f"{title}\n{link}", link)
        if new:
            msgs.extend(new)
            session.merge(Setting(key=key, value=now))
    for row in session.scalars(select(Setting).where(Setting.key.startswith(ALERT_PREFIX)).order_by(Setting.key)):
        source = row.key[len(ALERT_PREFIX):]
        h = health.get(source)
        if h is None or h["failed_after"] != 0:
            continue
        title = f"{source} works again"
        link = f"{base}/captures?{urlencode({'source': source})}"
        new = alert_messages(session, title, f"{title}\n{link}", link)
        if new:
            msgs.extend(new)
            session.delete(row)
    return msgs
