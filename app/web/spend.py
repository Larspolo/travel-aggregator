"""The page "Travel per year" (#1364): the booked journeys per year and per mode."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login
from app.currency import load_rates
from app.db import get_session
from app.models import Itinerary, ScoreProfile
from app.profiles import default_weights
from app.spend import year_summary
from app.web.pages import templates

router = APIRouter()


@router.get("/upcoming/years", dependencies=[Depends(require_login)])
def years(request: Request, session: Session = Depends(get_session)):
    itineraries = session.scalars(
        select(Itinerary).where(Itinerary.booked.is_(True)).options(selectinload(Itinerary.legs))).all()
    profile = session.scalars(select(ScoreProfile).where(ScoreProfile.is_default.is_(True))).first()
    # the CO₂ note names the profile of the kg per hour (#1465)
    return templates.TemplateResponse(request, "spend.html", {
        "years": year_summary(itineraries, load_rates(session), default_weights(session)),
        "co2_profile": profile.name if profile is not None else "default"})
