"""A prefilled GitHub issue for a failing source (#929): the owner reads the text and submits it (P4: no token,
no request from the app). The text holds no private data (P5): only counts, versions and masked reasons."""

import os
import re
from collections import Counter
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Capture
from app.parsers import get_parser
from app.sourcehealth import failed_clause, source_health

MAX_URL = 8000
MAX_REASONS = 10
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_DIGITS = re.compile(r"\d+")


def mask(reason: str) -> str:
    """Replace each quoted text with '…' and each run of digits with N; keep 200 characters."""
    return _DIGITS.sub("N", _QUOTED.sub("'…'", reason))[:200]


def _failed(session: Session, source: str) -> tuple[str | None, list[Capture]]:
    health = next((h for h in source_health(session) if h["source"] == source), None)
    last_good = health["last_good_at"] if health else None
    query = select(Capture).where(failed_clause(), Capture.source == source)
    if last_good is not None:
        query = query.where(Capture.captured_at > last_good)
    return (health["parser_version"] if health else None), list(session.scalars(query).all())


def report(session: Session, source: str, reasons_limit: int = MAX_REASONS) -> tuple[str, str]:
    """The title and the body of the issue, from the failed captures after the last good capture."""
    good_version, captures = _failed(session, source)
    parser = get_parser(source)
    version = parser.version if parser else (good_version or "-")
    reasons: Counter[str] = Counter()
    unreadable = rejected = 0
    for c in captures:
        if c.unreadable:
            unreadable += 1
            reasons[mask(c.unreadable)] += 1
        rejected += c.rejected_count or 0
        for e in c.errors_json or []:
            reasons[mask(str(e.get("reason", "")))] += 1
    title = f"Parser of {source} fails: {len(captures)} failed captures"
    lines = [f"Source: {source}", f"Parser version: {version}", f"Commit: {os.environ.get('GIT_SHA', 'dev')}",
             f"Failed captures after the last good capture: {len(captures)}",
             f"Unreadable payloads: {unreadable}", f"Rejected offers: {rejected}", "", "Most frequent reasons:"]
    lines += [f"- {count} × {reason}" for reason, count in reasons.most_common(reasons_limit)] or ["- none"]
    lines += ["", "Owner: please attach a trimmed payload of a failed capture (an agent cannot capture one, P1)."]
    return title, "\n".join(lines)


def report_url(session: Session, source: str) -> str:
    """The link to GitHub's new-issue form, at most MAX_URL characters (the reasons list is cut first)."""
    base = get_settings().issues_url
    for limit in range(MAX_REASONS, -1, -1):
        title, body = report(session, source, limit)
        url = f"{base}?{urlencode({'title': title, 'body': body})}"
        if len(url) <= MAX_URL:
            return url
    return url[:MAX_URL]
