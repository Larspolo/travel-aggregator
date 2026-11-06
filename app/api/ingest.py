"""POST /api/ingest: the captured offers of a userscript (docs/SPEC.md section 5)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import ingest
from app.auth import require_token
from app.db import get_session
from app.models import ApiToken, Trip
from app.schemas import IngestIn

router = APIRouter()


@router.post("/ingest")
def post_ingest(body: IngestIn, _: ApiToken = Depends(require_token),
                session: Session = Depends(get_session)) -> dict[str, int]:
    if session.get(Trip, body.trip_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {body.trip_id}")
    return ingest.store(session, body)
