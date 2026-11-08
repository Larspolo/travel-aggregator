"""The import page of the JSON export of a trip (#777): the owner uploads an export file, and the app adds its rows
to a new trip or to a trip of `planning` status with `import_trip()` (#776)."""

import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import Trip
from app.schemas import MAX_BODY_BYTES
from app.trip_import import import_trip
from app.web.pages import templates

router = APIRouter()


def _trips(session: Session) -> list[Trip]:
    return list(session.scalars(select(Trip).where(Trip.status == "planning").order_by(Trip.id.desc())))


def match_key(title, origin, destination, date_from, date_to) -> str:
    """The key of a trip that `trip_import.js` compares with the trip of the selected file: the same key preselects
    the trip, so that a second import of a file goes into the trip of the first import."""
    return json.dumps([title, origin or None, destination or None,
                       date_from.isoformat() if date_from else None, date_to.isoformat() if date_to else None],
                      ensure_ascii=False, separators=(",", ":"))  # the same text as JSON.stringify


def _page(request: Request, session: Session, selected: int | None = None, errors: list[str] | None = None,
          code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, "trip_import.html",
                                      {"trips": _trips(session), "selected": selected, "errors": errors or [],
                                       "match_key": match_key},
                                      status_code=code)


@router.get("/trips/import", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def import_form(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _page(request, session)


@router.post("/trips/import", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def import_file(request: Request, file: UploadFile | None = File(None), target: str = Form(""),
                      session: Session = Depends(get_session)):
    trip_id = int(target) if target.isdigit() else None
    raw = await file.read(MAX_BODY_BYTES + 1) if file is not None else b""
    if not raw:
        return _page(request, session, trip_id, ["Select an export file."], 400)
    if len(raw) > MAX_BODY_BYTES:
        return _page(request, session, trip_id, [f"The file is larger than {MAX_BODY_BYTES} bytes."], 400)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return _page(request, session, trip_id, ["The file is not JSON."], 400)
    if trip_id is not None and trip_id not in {t.id for t in _trips(session)}:
        return _page(request, session, None, ["Select a trip of the list."], 400)
    try:
        r = import_trip(session, data, trip_id)
    except ValueError as e:
        session.rollback()
        return _page(request, session, trip_id, [str(e)], 400)
    session.commit()
    unchanged = r.itineraries_unchanged + r.fares_unchanged + r.prices_unchanged
    request.session["flash"] = (f"Imported {r.itineraries_added} itineraries, {r.fares_added} fares and "
                                f"{r.prices_added} prices; {unchanged} unchanged")
    return RedirectResponse(f"/trips/{r.trip_id}", status_code=303)

