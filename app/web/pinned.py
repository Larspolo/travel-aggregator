"""The Pinned page (#1299): the pinned, not hidden offers of all trips in planning, in the order of departure.
The navigation shows their count (#1301)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import SESSION_KEY, require_login
from app.db import get_session
from app.models import Itinerary, Trip
from app.web.pages import templates

router = APIRouter()


def _pinned_select():
    return (select(Itinerary)
            .join(Trip, Itinerary.trip_id == Trip.id)
            .where(Itinerary.pinned.is_(True), Itinerary.hidden.is_(False), Trip.status == "planning"))


@router.get("/pinned", dependencies=[Depends(require_login)])
def pinned(request: Request, session: Session = Depends(get_session)):
    itineraries = session.scalars(
        _pinned_select()
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.fares), selectinload(Itinerary.trip))
        .order_by(Itinerary.depart_at, Itinerary.id)
    ).all()
    rows = [(it, min(it.fares, key=lambda f: f.latest_price) if it.fares else None) for it in itineraries]
    return templates.TemplateResponse(request, "pinned.html", {
        "rows": rows, "now": datetime.now(timezone.utc)})


def pinned_count(request: Request) -> int:
    """The number of pinned offers for the navigation (#1301): 0 with no login, so the login page reads no data."""
    if not request.session.get(SESSION_KEY):
        return 0
    # The same dependency as the routes, so that a test that overrides get_session also overrides this count.
    dependency = request.app.dependency_overrides.get(get_session, get_session)
    gen = dependency()
    session = next(gen)
    try:
        return session.scalar(select(func.count()).select_from(_pinned_select().subquery())) or 0
    finally:
        gen.close()


templates.env.globals["pinned_count"] = pinned_count
