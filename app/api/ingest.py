"""POST /api/ingest: the captured offers of a userscript (docs/SPEC.md section 5)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import ingest, notify
from app.auth import require_token
from app.db import get_session
from app.models import ApiToken, Trip
from app.schemas import IngestIn

router = APIRouter()


@router.post("/ingest")
def post_ingest(body: IngestIn, request: Request, tasks: BackgroundTasks, _: ApiToken = Depends(require_token),
                session: Session = Depends(get_session)) -> dict:
    if session.get(Trip, body.trip_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {body.trip_id}")
    drops: list[notify.PriceDrop] = []
    result = ingest.store(session, body, drops)
    msgs = notify.messages(session, drops, str(request.base_url))
    if msgs:  # after the response, so the userscript does not wait (#512)
        tasks.add_task(notify.deliver, msgs)
    return result
