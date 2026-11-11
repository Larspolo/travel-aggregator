"""The settings page "Days off" (#2370): add, change and delete the days off of the owner."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import DayOff
from app.web.pages import templates

router = APIRouter()


def _page(request: Request, session: Session, error: str | None = None, code: int = 200) -> HTMLResponse:
    rows = session.scalars(select(DayOff).order_by(DayOff.first_day, DayOff.id)).all()
    return templates.TemplateResponse(request, "days_off.html", {"rows": rows, "error": error}, status_code=code)


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


@router.get("/days-off", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def days_off_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _page(request, session)


@router.post("/days-off", response_model=None, dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_day_off(request: Request, id: str = Form(""), first_day: str = Form(""), last_day: str = Form(""),
                 note: str = Form(""), session: Session = Depends(get_session)) -> HTMLResponse | RedirectResponse:
    """Add a day off, or change the day off with the `id`. An empty last day is the first day."""
    row = None
    if id.strip():
        row = session.get(DayOff, int(id)) if id.strip().isdigit() else None
        if row is None:
            return _page(request, session, "The day off is not known.", 404)
    first = _day(first_day)
    last = _day(last_day) if last_day.strip() else first
    if first is None or last is None or last < first:
        return _page(request, session, "Give a valid first day; the last day must be empty or on or after the first day.", 422)
    note = note.strip()
    if len(note) > 100:
        return _page(request, session, "The note must have at most 100 characters.", 422)
    if row is None:
        row = DayOff()
        session.add(row)
    row.first_day, row.last_day, row.note = first, last, note
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse("/days-off", status_code=303)


@router.post("/days-off/{day_off_id}/delete", response_model=None,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_day_off(day_off_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    row = session.get(DayOff, day_off_id)
    if row is not None:
        session.delete(row)
        session.commit()
    return RedirectResponse("/days-off", status_code=303)
