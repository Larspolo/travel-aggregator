"""The page "Travel per year" (#1364): the booked journeys per year and per mode."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login, verify_csrf
from app.currency import load_rates
from app.delay_claim import claim
from app.db import get_session
from app.models import Itinerary, ScoreProfile
from app.profiles import default_weights
from app.spend import year_summary
from app.web.pages import templates

router = APIRouter()


@router.get("/upcoming/years", dependencies=[Depends(require_login)])
def years(request: Request, session: Session = Depends(get_session)):
    itineraries = session.scalars(
        select(Itinerary).where(Itinerary.booked.is_(True))
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.trip))).all()
    # the open delay claims, newest first (#1693)
    claims = sorted(((it, c) for it in itineraries if it.claim_paid_at is None and (c := claim(it)) is not None),
                    key=lambda p: p[0].depart_at, reverse=True)
    profile = session.scalars(select(ScoreProfile).where(ScoreProfile.is_default.is_(True))).first()
    # the CO₂ note names the profile of the kg per hour (#1465)
    return templates.TemplateResponse(request, "spend.html", {
        "years": year_summary(itineraries, load_rates(session), default_weights(session)),
        "claims": claims,
        "co2_profile": profile.name if profile is not None else "default"})


@router.post("/upcoming/years/claims/{itinerary_id}/paid", dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_claim_paid(itinerary_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """"Claim paid" marks the claim of a booked journey as done; a second POST opens it again (#1693)."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or not it.booked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no booked itinerary {itinerary_id}")
    it.claim_paid_at = None if it.claim_paid_at else datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse("/upcoming/years", status_code=303)
