"""The Upcoming page (#862): the booked itineraries of all trips that did not arrive yet, in the order of departure."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login
from app.db import get_session
from app.models import Itinerary
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
    return templates.TemplateResponse(request, "upcoming.html", {"itineraries": itineraries})
