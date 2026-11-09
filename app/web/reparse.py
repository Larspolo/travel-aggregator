"""The captures of a trip and the "reparse capture" action (#154): after a parser fix, the owner runs the current
parser version again on the stored raw data of a capture."""

import gzip
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ingest
from app.failure_report import report_url
from app.sourcehealth import add_old_script, failed_clause, source_health
from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import Capture, Trip
from app.parsers import get_parser, parser_classes
from app.schemas import MAX_BODY_BYTES, IngestIn
from app.web.pages import _get_trip, templates

router = APIRouter()

REPARSE_LIMIT = 500


@router.get("/trips/{trip_id}/captures", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def captures_page(request: Request, trip_id: int, failed: bool = False,
                  session: Session = Depends(get_session)) -> HTMLResponse:
    return _trip_captures(request, session, trip_id, failed)


def _upload_sources() -> list[str]:
    return [s for s in parser_classes() if s != "manual"]


FILE_NAME_ERROR = "Choose the source: the file name does not name one"


def _source_from_name(filename: str | None) -> str | None:
    """The source of a downloaded file `<source>-<id>.json`, as in #1291 (#1339)."""
    match = re.fullmatch(r"(.+)-\d+\.json", filename or "")
    return match.group(1) if match else None


@router.post("/trips/{trip_id}/captures/upload", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def upload_capture(request: Request, trip_id: int, file: UploadFile | None = File(None),
                         source: str = Form(""), session: Session = Depends(get_session)):
    """Store an uploaded payload file as a capture of the trip and parse it (#1338), as a capture of a userscript.
    With no source the source comes from the file name (#1339)."""
    _get_trip(session, trip_id)
    raw = await file.read(MAX_BODY_BYTES + 1) if file is not None else b""
    error = None
    from_name = source == ""
    if from_name:
        source = _source_from_name(file.filename if file is not None else None) or ""
    if source not in _upload_sources():
        error = FILE_NAME_ERROR if from_name else "Select a source that has a parser."
    elif not raw:
        error = "Select a payload file."
    elif len(raw) > MAX_BODY_BYTES:
        error = f"The file is larger than {MAX_BODY_BYTES} bytes."
    else:
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            error = "The file is not JSON."
    if error:
        return _trip_captures(request, session, trip_id, False, error, 400)
    body = IngestIn(trip_id=trip_id, source=source, parser_version=parser_classes()[source].version,
                    captured_at=datetime.now(timezone.utc), raw=data)
    ingest.store(session, body)
    return RedirectResponse(f"/trips/{trip_id}/captures", status_code=303)


def _trip_captures(request: Request, session: Session, trip_id: int, failed: bool, upload_error: str | None = None,
                   code: int = 200) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    query = select(Capture).where(Capture.trip_id == trip_id)
    if failed:
        query = query.where(failed_clause())
    captures = session.scalars(query.order_by(Capture.captured_at.desc(), Capture.id.desc())).all()
    return templates.TemplateResponse(request, "captures.html",
                                      {"trip": trip, "captures": captures, "failed": failed, "now": datetime.now(timezone.utc),
                                       "trip_travelers": {trip.id: trip.travelers},
                                       "move_trips": _move_trips(session),
                                       "failed_sources": _failed_sources(session) if failed else [],
                                       "upload_sources": _upload_sources(), "upload_error": upload_error},
                                      status_code=code)


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
    trips = session.scalars(select(Trip).where(Trip.id.in_(trip_ids))).all()
    trip_titles = {t.id: t.title for t in trips}
    return templates.TemplateResponse(request, "captures.html",
                                      {"trip": None, "captures": captures, "trip_titles": trip_titles, "failed": failed,
                                       "trip_travelers": {t.id: t.travelers for t in trips},
                                       "source": source, "sources": [] if failed or source else add_old_script(source_health(session)), "now": datetime.now(timezone.utc),
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


def _failed_sources(session: Session, source: str | None = None) -> list[dict]:
    query = select(Capture.source).where(failed_clause(), Capture.raw_gz.is_not(None)).distinct()
    if source:
        query = query.where(Capture.source == source)
    return [{"source": s, "report_url": report_url(session, s)} for s in sorted(session.scalars(query).all())]


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


RAW_LIMIT = 200_000


@router.get("/captures/{capture_id}/raw", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def capture_raw_page(request: Request, capture_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    """The stored raw payload of one capture as formatted JSON (#1290). Autoescape makes it text (P5)."""
    capture = session.get(Capture, capture_id)
    if capture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no capture {capture_id}")
    text = None
    size_kb = 0
    if capture.raw_gz is not None:
        data = gzip.decompress(capture.raw_gz).decode("utf-8")
        try:
            text = json.dumps(json.loads(data), indent=2, ensure_ascii=False)
        except ValueError:
            text = data
        size_kb = max(1, round(len(text.encode("utf-8")) / 1024))
    truncated = text is not None and len(text) > RAW_LIMIT
    return templates.TemplateResponse(request, "capture_raw.html",
                                      {"capture": capture, "text": text[:RAW_LIMIT] if truncated else text,
                                       "truncated": truncated, "size_kb": size_kb})


@router.get("/captures/{capture_id}/raw.json", dependencies=[Depends(require_login)])
def capture_raw_download(capture_id: int, session: Session = Depends(get_session)) -> Response:
    """The full raw payload of one capture as a JSON file (#1291), to attach it to a parser issue."""
    capture = session.get(Capture, capture_id)
    if capture is None or capture.raw_gz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no raw payload for capture {capture_id}")
    safe_source = re.sub(r"[^A-Za-z0-9.-]", "", capture.source)
    return Response(gzip.decompress(capture.raw_gz), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{safe_source}-{capture.id}.json"'})


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
