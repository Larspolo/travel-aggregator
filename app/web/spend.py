"""The page "Travel per year" (#1364): the booked journeys per year and per mode."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login, verify_csrf
from app.currency import load_rates
from app.delay_claim import claim
from app.db import get_session
from app.models import Itinerary, ScoreProfile
from app.profiles import default_weights
from app.spend import year_rows, year_summary
from app.web.export import year_csv
from app.web.pages import templates

router = APIRouter()


def _booked(session: Session) -> list[Itinerary]:
    """The booked and the cancelled itineraries; a cancelled booking keeps its paid price less the refund (#1687)."""
    return session.scalars(
        select(Itinerary).where(or_(Itinerary.booked.is_(True), Itinerary.cancelled_at.is_not(None)))
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.trip))).all()


@router.get("/upcoming/years", dependencies=[Depends(require_login)])
def years(request: Request, session: Session = Depends(get_session)):
    itineraries = _booked(session)
    # the open delay claims, newest first (#1693); claim() is None for a cancelled booking (not booked)
    claims = sorted(((it, c) for it in itineraries if it.claim_paid_at is None and (c := claim(it)) is not None),
                    key=lambda p: p[0].depart_at, reverse=True)
    profile = session.scalars(select(ScoreProfile).where(ScoreProfile.is_default.is_(True))).first()
    # the CO₂ note names the profile of the kg per hour (#1465)
    return templates.TemplateResponse(request, "spend.html", {
        "years": year_summary(itineraries, load_rates(session), default_weights(session)),
        "claims": claims,
        "co2_profile": profile.name if profile is not None else "default"})


@router.get("/upcoming/years/{year}/export.csv", dependencies=[Depends(require_login)])
def export_year_csv(year: int, session: Session = Depends(get_session)) -> Response:
    """The CSV file of the journeys of one year of the page (#1729, #1730)."""
    rows = year_rows(_booked(session), year, load_rates(session))
    return Response(year_csv(rows), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="travel-{year}.csv"'})


@router.post("/upcoming/years/claims/{itinerary_id}/paid", dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_claim_paid(itinerary_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """"Claim paid" marks the claim of a booked journey as done; a second POST opens it again (#1693)."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or not it.booked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no booked itinerary {itinerary_id}")
    it.claim_paid_at = None if it.claim_paid_at else datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse("/upcoming/years", status_code=303)
