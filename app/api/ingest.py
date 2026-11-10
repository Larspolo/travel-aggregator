"""POST /api/ingest: the captured offers of a userscript (docs/SPEC.md section 5)."""

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import ingest, notify
from app.backup import stale_backup_messages
from app.sourcehealth import source_alert_messages
from app.auth import require_token
from app.db import get_session
from app.models import ApiToken, Setting, SilentPage, Trip
from app.reminder import BASE_URL_KEY
from app.schemas import IngestIn, SilentIn

router = APIRouter()


@router.post("/ingest")
def post_ingest(body: IngestIn, request: Request, tasks: BackgroundTasks, _: ApiToken = Depends(require_token),
                session: Session = Depends(get_session)) -> dict:
    if session.get(Trip, body.trip_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {body.trip_id}")
    drops: list[notify.PriceDrop] = []
    result = ingest.store(session, body, drops)
    base_url = str(request.base_url)
    msgs = notify.messages(session, drops, base_url)
    if notify.setting(session, BASE_URL_KEY) != base_url:  # the link of the reminders of the backup loop (#1119)
        session.merge(Setting(key=BASE_URL_KEY, value=base_url))
        session.commit()
    try:  # the backup service can stop with no message of its own (#1088)
        msgs += stale_backup_messages(session, Path(os.environ.get("BACKUP_DIR", "/backups")), datetime.now(UTC))
    except Exception:  # noqa: BLE001 (a backup check must not break the ingest)
        session.rollback()
    try:  # a source that fails, or works again, after its captures (#1173)
        msgs += source_alert_messages(session, base_url)
        session.commit()
    except Exception:  # noqa: BLE001 (an alert check must not break the ingest)
        session.rollback()
    if msgs:  # after the response, so the userscript does not wait (#512)
        # a new session: the session of the request is closed then (the tests override get_session)
        new_session = contextmanager(request.app.dependency_overrides.get(get_session, get_session))
        tasks.add_task(notify.deliver, msgs, new_session)
    return result


@router.post("/silent")
def post_silent(body: SilentIn, _: ApiToken = Depends(require_token),
                session: Session = Depends(get_session)) -> dict[str, int]:
    """A results page with no offers seen (#1755): store only the four fields (P5)."""
    row = SilentPage(source=body.source, page_url=body.page_url, seen_at=body.seen_at,
                     script_version=body.script_version)
    session.add(row)
    session.commit()
    return {"id": row.id}
