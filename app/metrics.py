"""The metrics of the app for Prometheus (#1892): GET /metrics with the metrics token. The database holds only the hash
of the token (P5)."""

import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import bearer, hash_token, require_login, verify_csrf
from app.backup import CHECK_KEY, newest_backup
from app.db import get_session
from app.models import Capture, Itinerary, Setting, Trip
from app.sourcehealth import failed_clause, source_health

KEY = "metrics_token_hash"
MEDIA_TYPE = "text/plain; version=0.0.4"

router = APIRouter()


def new_metrics_token(session: Session) -> str:
    """Give a new metrics token. It replaces the last token: the old token stops."""
    token = secrets.token_urlsafe(32)
    setting = session.get(Setting, KEY)
    if setting is None:
        session.add(Setting(key=KEY, value=hash_token(token)))
    else:
        setting.value = hash_token(token)
    return token


def revoke_metrics_token(session: Session) -> None:
    setting = session.get(Setting, KEY)
    if setting is not None:
        session.delete(setting)


def metrics_token_ok(session: Session, token: str) -> bool:
    """True if the token is the metrics token. The hash is compared in constant time."""
    setting = session.get(Setting, KEY)
    if setting is None or not setting.value:
        return False
    return hmac.compare_digest(setting.value.encode(), hash_token(token).encode())


def backup_values(session: Session, backup_dir: Path, now: datetime) -> list[tuple[str, str, float]]:
    """The backup gauges (#1894): the age and the size of the newest dump, and the result of its check.

    A gauge has no value (and no line) when there is no backup, or no check result.
    """
    values = []
    newest = newest_backup(backup_dir)
    if newest is not None:
        when, size = newest
        values += [
            ("travel_backup_age_seconds", "Seconds since the newest backup.", (now - when).total_seconds()),
            ("travel_backup_size_bytes", "Size of the newest backup in bytes.", size),
        ]
    setting = session.get(Setting, CHECK_KEY)
    try:
        data = json.loads(setting.value) if setting is not None else None
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict) and ("error" in data or "tables" in data):
        ok = 0 if "error" in data else 1
        values.append(("travel_backup_check_ok", "1 if the check of the newest backup read the dump, else 0.", ok))
    return values


def label_value(value: str) -> str:
    """Escape a label value as the text format says: a backslash, a double quote and a line break."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def source_lines(session: Session, now: datetime) -> list[str]:
    """Per source: the count of captures, the failed captures and the age of the last good capture (#1893)."""
    counts = session.execute(select(Capture.source, func.count(Capture.id)).group_by(Capture.source)).all()
    failures = dict(session.execute(select(Capture.source, func.count(Capture.id).filter(failed_clause()))
                                    .group_by(Capture.source)).all())
    last_good = {row["source"]: row["last_good_at"] for row in source_health(session)}
    lines = [
        "# HELP travel_captures_total The count of captures per source.",
        "# TYPE travel_captures_total counter",
    ]
    lines += [f'travel_captures_total{{source="{label_value(src)}"}} {n}' for src, n in sorted(counts)]
    lines += [
        "# HELP travel_capture_failures_total The count of failed captures per source.",
        "# TYPE travel_capture_failures_total counter",
    ]
    lines += [f'travel_capture_failures_total{{source="{label_value(src)}"}} {failures.get(src, 0)}'
              for src, _ in sorted(counts)]
    lines += [
        "# HELP travel_last_good_capture_age_seconds The seconds since the last good capture per source.",
        "# TYPE travel_last_good_capture_age_seconds gauge",
    ]
    for src, _ in sorted(counts):
        at = last_good.get(src)
        if at is not None:
            age = int((now - at).total_seconds())
            lines.append(f'travel_last_good_capture_age_seconds{{source="{label_value(src)}"}} {age}')
    return lines


def metrics_text(session: Session) -> str:
    """The body in the text format of Prometheus."""
    values = [
        ("travel_trips", "The count of trips, also the archived trips.", session.scalar(select(func.count(Trip.id)))),
        ("travel_offers", "The count of itineraries.", session.scalar(select(func.count(Itinerary.id)))),
    ]
    values += backup_values(session, Path(os.environ.get("BACKUP_DIR", "/backups")), datetime.now(UTC))
    lines = []
    for name, help_text, value in values:
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]
    lines += source_lines(session, datetime.now(UTC))
    return "\n".join(lines) + "\n"


@router.get("/metrics")
def metrics(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
            session: Session = Depends(get_session)) -> PlainTextResponse:
    if credentials is None or not metrics_token_ok(session, credentials.credentials):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing metrics token",
                            headers={"WWW-Authenticate": "Bearer"})
    return PlainTextResponse(metrics_text(session), media_type=MEDIA_TYPE)


@router.post("/settings/metrics-token", dependencies=[Depends(require_login), Depends(verify_csrf)])
def make_token(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    token = new_metrics_token(session)
    session.commit()
    request.session["metrics_token"] = token  # the settings page shows it once
    return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/metrics-token/revoke", dependencies=[Depends(require_login), Depends(verify_csrf)])
def stop_token(session: Session = Depends(get_session)) -> RedirectResponse:
    revoke_metrics_token(session)
    session.commit()
    return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)
