"""The settings page "Rail passes" (#2265): add, change and delete the rail passes of the owner."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import RailPass
from app.web.pages import templates

router = APIRouter()


def _page(request: Request, session: Session, error: str | None = None, code: int = 200) -> HTMLResponse:
    rows = session.scalars(select(RailPass).order_by(RailPass.first_day, RailPass.name)).all()
    return templates.TemplateResponse(request, "passes.html", {"rows": rows, "error": error}, status_code=code)


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def _cost(text: str) -> Decimal | None:
    """A cost from 0 to 1000 with at most 2 decimals (the rule of the booking fee, #1142), else None."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > Decimal("1000") or value.as_tuple().exponent < -2:
        return None
    return value


@router.get("/passes", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def passes_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _page(request, session)


@router.post("/passes", response_model=None, dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_pass(request: Request, id: str = Form(""), name: str = Form(""), first_day: str = Form(""),
              last_day: str = Form(""), day_cost: str = Form(""), carriers: str = Form(""),
              session: Session = Depends(get_session)) -> HTMLResponse | RedirectResponse:
    """Add a pass, or change the pass with the `id`."""
    row = None
    if id.strip():
        row = session.get(RailPass, int(id)) if id.strip().isdigit() else None
        if row is None:
            return _page(request, session, "The pass is not known.", 404)
    name = name.strip()
    if not 1 <= len(name) <= 100:
        return _page(request, session, "The name must have 1 to 100 characters.", 422)
    other = session.scalars(select(RailPass).where(RailPass.name == name)).first()
    if other is not None and other is not row:
        return _page(request, session, "Another pass has this name.", 422)
    first, last = _day(first_day), _day(last_day)
    if first is None or last is None or last < first:
        return _page(request, session, "Give two valid dates; the last day must be on or after the first day.", 422)
    cost = _cost(day_cost)
    if cost is None:
        return _page(request, session, "The cost per day must be a number from 0 to 1000 with at most 2 decimals.", 422)
    carriers = carriers.strip()
    if len(carriers) > 300:
        return _page(request, session, "The carriers must have at most 300 characters.", 422)
    if row is None:
        row = RailPass()
        session.add(row)
    row.name, row.first_day, row.last_day, row.day_cost, row.carriers = name, first, last, cost, carriers
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse("/passes", status_code=303)


@router.post("/passes/{pass_id}/delete", response_model=None,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_pass(pass_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    row = session.get(RailPass, pass_id)
    if row is not None:
        session.delete(row)
        session.commit()
    return RedirectResponse("/passes", status_code=303)
