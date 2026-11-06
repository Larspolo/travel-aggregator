"""The captures of a trip and the "reparse capture" action (#154): after a parser fix, the owner runs the current
parser version again on the stored raw data of a capture."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ingest
from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import Capture, Trip
from app.parsers import get_parser
from app.web.pages import _get_trip, templates

router = APIRouter()


@router.get("/trips/{trip_id}/captures", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def captures_page(request: Request, trip_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    captures = session.scalars(select(Capture).where(Capture.trip_id == trip_id)
                               .order_by(Capture.captured_at.desc(), Capture.id.desc())).all()
    return templates.TemplateResponse(request, "captures.html", {"trip": trip, "captures": captures})


@router.get("/captures", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def all_captures_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """The newest 200 captures of all trips (#347): a format change of a site shows in one place."""
    captures = session.scalars(select(Capture).order_by(Capture.captured_at.desc(), Capture.id.desc())
                               .limit(200)).all()
    trip_ids = {c.trip_id for c in captures}
    trip_titles = {t.id: t.title for t in session.scalars(select(Trip).where(Trip.id.in_(trip_ids))).all()}
    return templates.TemplateResponse(request, "captures.html",
                                      {"trip": None, "captures": captures, "trip_titles": trip_titles})


@router.post("/captures/{capture_id}/reparse", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def reparse_capture(request: Request, capture_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    capture = session.get(Capture, capture_id)
    if capture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no capture {capture_id}")
    parser = get_parser(capture.source)
    counts = ingest.reparse(session, capture)
    if counts is None:
        message = ("This capture has no raw data: there is nothing to reparse." if capture.raw_gz is None
                   else f"The source {capture.source} has no parser: there is nothing to reparse.")
    elif counts["unreadable"]:
        message = f"The parser cannot read the raw data: {counts['unreadable']}"
    else:
        message = (f"Reparsed with {capture.source} {parser.version}: {counts['created']} created, "
                   f"{counts['updated']} updated, {counts['unchanged']} unchanged, {counts['rejected']} rejected.")
    return HTMLResponse(f'<span class="reparse-result">{_escape(message)}</span>')


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
