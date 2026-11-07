"""The captures of a trip and the "reparse capture" action (#154): after a parser fix, the owner runs the current
parser version again on the stored raw data of a capture."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ingest
from app.sourcehealth import failed_clause, source_health
from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import Capture, Trip
from app.parsers import get_parser
from app.web.pages import _get_trip, templates

router = APIRouter()

REPARSE_LIMIT = 500


@router.get("/trips/{trip_id}/captures", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def captures_page(request: Request, trip_id: int, failed: bool = False,
                  session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    query = select(Capture).where(Capture.trip_id == trip_id)
    if failed:
        query = query.where(failed_clause())
    captures = session.scalars(query.order_by(Capture.captured_at.desc(), Capture.id.desc())).all()
    return templates.TemplateResponse(request, "captures.html",
                                      {"trip": trip, "captures": captures, "failed": failed, "now": datetime.now(timezone.utc),
                                       "move_trips": _move_trips(session),
                                       "failed_sources": _failed_sources(session) if failed else []})


@router.get("/captures", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def all_captures_page(request: Request, failed: bool = False, source: str | None = Query(None, max_length=50),
                      session: Session = Depends(get_session)) -> HTMLResponse:
    """The newest 200 captures of all trips (#347): a format change of a site shows in one place.
    With `source` (#725) only the captures of that source; `failed` and `source` combine."""
    query = select(Capture)
    if failed:
        query = query.where(failed_clause())
    if source:
        query = query.where(Capture.source == source)
    captures = session.scalars(query.order_by(Capture.captured_at.desc(), Capture.id.desc()).limit(200)).all()
    trip_ids = {c.trip_id for c in captures}
    trip_titles = {t.id: t.title for t in session.scalars(select(Trip).where(Trip.id.in_(trip_ids))).all()}
    return templates.TemplateResponse(request, "captures.html",
                                      {"trip": None, "captures": captures, "trip_titles": trip_titles, "failed": failed,
                                       "source": source, "sources": [] if failed or source else source_health(session), "now": datetime.now(timezone.utc),
                                       "move_trips": _move_trips(session),
                                       "failed_sources": _failed_sources(session, source) if failed else []})


@router.post("/captures/reparse-failed", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def reparse_failed(source: str = Form(...), session: Session = Depends(get_session)) -> HTMLResponse:
    """Reparse all failed captures of one source with raw data (#489), at most REPARSE_LIMIT in one request."""
    parser = get_parser(source)
    if parser is None:
        return HTMLResponse(f'<span class="reparse-result">{_escape(f"The source {source} has no parser.")}</span>')
    query = select(Capture).where(failed_clause(), Capture.source == source, Capture.raw_gz.is_not(None))
    captures = session.scalars(query.order_by(Capture.id).limit(REPARSE_LIMIT + 1)).all()
    more = len(captures) > REPARSE_LIMIT
    ok = still = created = updated = 0
    for capture in captures[:REPARSE_LIMIT]:
        counts = ingest.reparse(session, capture)
        if counts is None:
            continue
        if counts["unreadable"] or counts["rejected"]:
            still += 1
        else:
            ok += 1
        created += counts["created"]
        updated += counts["updated"]
    message = (f"Reparsed {ok + still} captures of {source} with {parser.version}: {ok} now parse, {still} still fail; "
               f"{created} created, {updated} updated.")
    if more:
        message += f" More than {REPARSE_LIMIT} captures wait: click again."
    return HTMLResponse(f'<span class="reparse-result">{_escape(message)}</span>')


def _failed_sources(session: Session, source: str | None = None) -> list[str]:
    query = select(Capture.source).where(failed_clause(), Capture.raw_gz.is_not(None)).distinct()
    if source:
        query = query.where(Capture.source == source)
    return sorted(session.scalars(query).all())


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


@router.post("/captures/{capture_id}/move", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def move_capture(capture_id: int, trip_id: int = Form(...), session: Session = Depends(get_session)) -> HTMLResponse:
    """Move the offers of a capture into the wrong trip to the trip `trip_id` (#580, epic #578)."""
    capture = session.get(Capture, capture_id)
    if capture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no capture {capture_id}")
    target = session.get(Trip, trip_id)
    if target is None:
        message = f"There is no trip {trip_id}: nothing moved."
    elif target.id == capture.trip_id:
        message = "The capture is already in this trip: nothing moved."
    else:
        counts = ingest.move_capture(session, capture, target.id)
        if counts is None:
            message = ("This capture has no raw data: nothing moved." if capture.raw_gz is None
                       else f"The source {capture.source} has no parser: nothing moved.")
        elif counts["unreadable"]:
            message = f"The parser cannot read the raw data: {counts['unreadable']}. Nothing moved."
        else:
            message = (f"Moved to {target.title}: {counts['created']} created, {counts['updated']} updated, "
                       f"{counts['unchanged']} unchanged, {counts['rejected']} rejected.")
    return HTMLResponse(f'<span class="reparse-result">{_escape(message)}</span>')


def _move_trips(session: Session) -> list[Trip]:
    """The trips that a capture can move to: not archived, newest first (#580)."""
    query = select(Trip).where(Trip.status != "archived").order_by(Trip.created_at.desc(), Trip.id.desc())
    return list(session.scalars(query).all())


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
