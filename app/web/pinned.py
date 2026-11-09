"""The Pinned page (#1299): the pinned, not hidden offers of all trips in planning, in the order of departure."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login
from app.db import get_session
from app.models import Itinerary, Trip
from app.web.pages import templates

router = APIRouter()


@router.get("/pinned", dependencies=[Depends(require_login)])
def pinned(request: Request, session: Session = Depends(get_session)):
    itineraries = session.scalars(
        select(Itinerary)
        .join(Trip, Itinerary.trip_id == Trip.id)
        .where(Itinerary.pinned.is_(True), Itinerary.hidden.is_(False), Trip.status == "planning")
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.fares), selectinload(Itinerary.trip))
        .order_by(Itinerary.depart_at, Itinerary.id)
    ).all()
    rows = [(it, min(it.fares, key=lambda f: f.latest_price) if it.fares else None) for it in itineraries]
    return templates.TemplateResponse(request, "pinned.html", {
        "rows": rows, "now": datetime.now(timezone.utc)})
