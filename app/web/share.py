"""The read-only page of a trip at a secret link (#903). The page shows no notes except the partner's own (#1782),
no booking links, captures or forms."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, subqueryload

from app.auth import require_login, token_limiter, verify_csrf
from app.db import get_session
from app.discount_cards import cards_warning, fare_cards
from app.models import AccessTime, Itinerary, ShareMark, Trip
from app.share import new_link, revoke, trip_for_token
from app.fees import load_fees
from app.web.pages import fare_travelers, format_breakdown, load_rates, resolve_weights, row_cost, templates

router = APIRouter()

PRIVATE_HEADERS = {"X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def _trip(session: Session, trip_id: int) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    return trip


@router.post("/trips/{trip_id}/share", dependencies=[Depends(require_login), Depends(verify_csrf)])
def share_trip(request: Request, trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    token = new_link(_trip(session, trip_id))
    session.commit()
    # the trip page shows the link once (as a new API token)
    request.session["share_link"] = str(request.url_for("shared_trip", token=token))
    return RedirectResponse(f"/trips/{trip_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/trips/{trip_id}/share/revoke", dependencies=[Depends(require_login), Depends(verify_csrf)])
def revoke_share(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    revoke(_trip(session, trip_id))
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/trips/{trip_id}/share/end", dependencies=[Depends(require_login), Depends(verify_csrf)])
def end_share(trip_id: int, share_ends_on: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    """Set the last day of the link (#2026). A blank value clears it; a past or non-ISO date gives 422 and no change."""
    trip = _trip(session, trip_id)
    value = share_ends_on.strip()
    if not value:
        trip.share_ends_on = None
    else:
        try:
            day = date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the end date is not a date (YYYY-MM-DD)")
        if day < datetime.now(timezone.utc).date():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the end date is in the past")
        trip.share_ends_on = day
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=status.HTTP_303_SEE_OTHER)


def _shared(request: Request, session: Session, token: str) -> Trip:
    """The trip of a share token. A bad token counts for the address (#904): 404, and 429 when the address is locked."""
    address = request.client.host if request.client else "unknown"
    wait = token_limiter.retry_after(address)
    if wait > 0:  # too many bad links of this address (#904): nobody can guess a link
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many bad share links",
                            headers={**PRIVATE_HEADERS, "Retry-After": str(wait)})
    trip = trip_for_token(session, token) if len(token) <= 100 else None
    if trip is None:
        token_limiter.failure(address)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no shared trip", headers=PRIVATE_HEADERS)
    return trip


NOTE_MAX = 200


@router.post("/s/{token}/marks/{itinerary_id}")
def toggle_mark(request: Request, token: str, itinerary_id: int,
                note: str | None = Form(None), edit: str | None = Form(None), remove: str | None = Form(None),
                session: Session = Depends(get_session)) -> RedirectResponse:
    """Set or remove the "Suits me" mark of the travel partner on one row (#1781). No login and no CSRF token: the
    secret token in the URL authorizes the request, as for the page. Only a row that the page shows can get a mark.
    A note (#1782) is set with the mark or with `edit`; `remove` deletes the mark and its note. A bare POST on a
    marked row still removes the mark (#1781)."""
    trip = _shared(request, session, token)
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip.id or it.hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such row", headers=PRIVATE_HEADERS)
    text = (note or "").strip() or None  # a blank note is no note
    if text is not None and len(text) > NOTE_MAX:
        raise HTTPException(422, f"a note has at most {NOTE_MAX} characters", headers=PRIVATE_HEADERS)
    mark = session.scalars(select(ShareMark).where(ShareMark.trip_id == trip.id,
                                                   ShareMark.itinerary_id == it.id)).one_or_none()
    if mark is None:
        session.add(ShareMark(trip_id=trip.id, itinerary_id=it.id, note=text))
    elif remove is not None or edit is None:
        session.delete(mark)
    else:
        mark.note = text
    session.commit()
    return RedirectResponse(f"/s/{token}#row-{it.id}", status_code=status.HTTP_303_SEE_OTHER, headers=PRIVATE_HEADERS)


@router.get("/s/{token}", response_class=HTMLResponse, name="shared_trip")
def shared_trip(request: Request, token: str, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _shared(request, session, token)
    weights, _ = resolve_weights(session, trip, {}, None)  # the profile of the trip, no overrides
    itineraries = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False))
                                  .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = session.scalars(select(AccessTime)).all()
    rates = load_rates(session)
    stale_before = datetime.now(timezone.utc) - timedelta(hours=weights.stale_hours)
    counts = fare_travelers(session, itineraries)  # the price per traveler (#767)
    fees = load_fees(session)  # the booking fees (#1143)
    rows = [(it, *row_cost(it, it.fares, places, weights, stale_before, rates, counts, fees)) for it in itineraries
            if it.fares and it.legs]
    rows.sort(key=lambda r: (r[2].total, r[0].depart_at))
    marks = {m.itinerary_id: m for m in session.scalars(select(ShareMark).where(ShareMark.trip_id == trip.id))}
    context = {"trip": trip, "rows": rows, "format_breakdown": format_breakdown, "token": token, "marks": marks,
               "cards_warning": cards_warning(itineraries, fare_cards(session, itineraries))}  # #1751
    return templates.TemplateResponse(request, "trip_shared.html", context, headers=PRIVATE_HEADERS)
