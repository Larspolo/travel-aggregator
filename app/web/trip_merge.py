"""The confirmation page and the POST of "Merge into" on the edit page of a trip (#1262): `merge_trips()` (#1261)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import Capture, Itinerary, Trip
from app.trip_merge import is_linked, merge_trips
from app.web.pages import templates

router = APIRouter()


def _trip(session: Session, trip_id: int) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    return trip


def _into(value: str) -> int:
    if not value.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "choose the trip to merge into")
    return int(value)


@router.get("/trips/{trip_id}/merge", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def merge_confirm(request: Request, trip_id: int, into: str = "", session: Session = Depends(get_session)):
    source = _trip(session, trip_id)
    target = _trip(session, _into(into))
    if target.id == source.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the source and the target are the same trip")
    if is_linked(session, source):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the source trip is linked to another trip")
    counts = {
        "itineraries": session.scalar(select(func.count(Itinerary.id)).where(Itinerary.trip_id == source.id)),
        "captures": session.scalar(select(func.count(Capture.id)).where(Capture.trip_id == source.id)),
    }
    return templates.TemplateResponse(request, "trip_merge.html", {"source": source, "target": target, "counts": counts})


@router.post("/trips/{trip_id}/merge", response_class=HTMLResponse, dependencies=[Depends(require_login), Depends(verify_csrf)])
def merge_post(trip_id: int, into: str = "", session: Session = Depends(get_session)):
    _trip(session, trip_id)
    target_id = _into(into)
    try:
        merge_trips(session, trip_id, target_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return RedirectResponse(f"/trips/{target_id}", status_code=303)
