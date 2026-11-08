"""The Upcoming page (#862): the booked itineraries of all trips that did not arrive yet, in the order of departure."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login, verify_csrf
from app.calendar_feed import KEY, new_feed_token, revoke_feed
from app.db import get_session
from app.models import Itinerary, Setting
from app.web.pages import templates

router = APIRouter()


@router.get("/upcoming", dependencies=[Depends(require_login)])
def upcoming(request: Request, session: Session = Depends(get_session)):
    itineraries = session.scalars(
        select(Itinerary)
        .where(Itinerary.booked.is_(True), Itinerary.arrive_at >= datetime.now(timezone.utc))
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.trip))
        .order_by(Itinerary.depart_at, Itinerary.id)
    ).all()
    since = session.get(Setting, SINCE) if session.get(Setting, KEY) is not None else None
    return templates.TemplateResponse(request, "upcoming.html", {
        "itineraries": itineraries, "now": datetime.now(timezone.utc),
        # the link shows once after "Subscribe" (#1113); the offline copy is a later GET with no link
        "feed_link": request.session.pop("calendar_feed_link", None),
        "feed_since": datetime.fromisoformat(since.value) if since is not None else None})


SINCE = "calendar_feed_at"


def _set_since(session: Session, value: str) -> None:
    setting = session.get(Setting, SINCE)
    if setting is None:
        session.add(Setting(key=SINCE, value=value))
    else:
        setting.value = value


@router.post("/upcoming/calendar", dependencies=[Depends(require_login), Depends(verify_csrf)])
def subscribe_calendar(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    token = new_feed_token(session)
    _set_since(session, datetime.now(timezone.utc).isoformat())
    session.commit()
    request.session["calendar_feed_link"] = str(request.url_for("calendar_feed", token=token))
    return RedirectResponse("/upcoming", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/upcoming/calendar/revoke", dependencies=[Depends(require_login), Depends(verify_csrf)])
def revoke_calendar(session: Session = Depends(get_session)) -> RedirectResponse:
    revoke_feed(session)
    since = session.get(Setting, SINCE)
    if since is not None:
        session.delete(since)
    session.commit()
    return RedirectResponse("/upcoming", status_code=status.HTTP_303_SEE_OTHER)
