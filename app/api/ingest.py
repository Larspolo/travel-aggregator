"""POST /api/ingest: the captured offers of a userscript (docs/SPEC.md section 5)."""

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import ingest, notify
from app.backup import stale_backup_messages
from app.auth import require_token
from app.db import get_session
from app.models import ApiToken, Setting, Trip
from app.reminder import BASE_URL_KEY
from app.schemas import IngestIn

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
    if msgs:  # after the response, so the userscript does not wait (#512)
        # a new session: the session of the request is closed then (the tests override get_session)
        new_session = contextmanager(request.app.dependency_overrides.get(get_session, get_session))
        tasks.add_task(notify.deliver, msgs, new_session)
    return result
