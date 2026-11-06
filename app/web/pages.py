"""The web pages: login, logout, the trips list, the trip page, the API tokens and the access and egress places. Jinja2 escapes all output: captured text is
untrusted (P5)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from pydantic import ValidationError
from sqlalchemy.orm import Session, subqueryload

from app.auth import SESSION_KEY, check_password, csrf_token, require_login, verify_csrf
from app.config import get_settings
from app.db import get_session
from app.door import door_extras, flight_extras
from app.models import AccessTime, ApiToken, Itinerary, Trip
from app.schemas import TripForm
from app.ranking import Weights, effective_cost, format_breakdown
from app.tokens import create as create_token, revoke as revoke_token
from app.trips import list_trips

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["csrf_token"] = csrf_token


def local(t: datetime, offset_min: int) -> datetime:
    """The time as the travel site showed it: UTC back to its original offset."""
    return t.astimezone(timezone(timedelta(minutes=offset_min)))


templates.env.filters["local"] = local

MODE_ICONS = {"train": "🚆", "bus": "🚌", "flight": "✈️"}


def mode_icon(mode: str) -> str:
    """The icon of one leg mode (a mode with no icon gets a dot)."""
    return MODE_ICONS.get(mode, "•")


def day_gap(arrive_local: datetime, depart_local: datetime) -> int:
    """How many local calendar days later the arrival is than the departure."""
    return (arrive_local.date() - depart_local.date()).days


def ago(t: datetime, now: datetime) -> str:
    """The age of a capture, for example '2 h ago'."""
    seconds = max(0, int((now - t).total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 48 * 3600:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} days ago"


templates.env.filters["mode_icon"] = mode_icon
templates.env.filters["day_gap"] = day_gap
templates.env.filters["ago"] = ago


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def login(request: Request, password: str = Form("")) -> HTMLResponse:
    if check_password(password, get_settings().owner_password_hash):
        request.session.clear()
        request.session[SESSION_KEY] = True
        csrf_token(request)  # a new token after the login
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Wrong password."}, status_code=401)


@router.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def index(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return templates.TemplateResponse(request, "trips.html", {"trips": list_trips(session)})


FORM_FIELDS = tuple(TripForm.model_fields)


def _form_page(request: Request, values: dict, errors: list[str], trip_id: int | None, code: int = 200):
    return templates.TemplateResponse(request, "trip_form.html",
                                      {"values": values, "errors": errors, "trip_id": trip_id}, status_code=code)


async def _save(request: Request, session: Session, trip: Trip | None):
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FORM_FIELDS}
    try:
        data = TripForm.model_validate(values)
    except ValidationError as e:
        errors = [f"{'.'.join(map(str, err['loc'])) or 'form'}: {err['msg']}" for err in e.errors()]
        return _form_page(request, values, errors, trip.id if trip else None, 422)
    if trip is None:
        trip = Trip()
        session.add(trip)
    for k, v in data.model_dump().items():
        setattr(trip, k, v)
    session.commit()
    return RedirectResponse("/", status_code=303)


def _get_trip(session: Session, trip_id: int) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    return trip


@router.get("/trips/new", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def new_trip_form(request: Request) -> HTMLResponse:
    return _form_page(request, {"travelers": 1, "status": "planning"}, [], None)


@router.post("/trips/new", response_class=HTMLResponse, dependencies=[Depends(require_login), Depends(verify_csrf)])
async def new_trip(request: Request, session: Session = Depends(get_session)):
    return await _save(request, session, None)


@router.get("/trips/{trip_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def edit_trip_form(request: Request, trip_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    values = {k: ("" if getattr(trip, k) is None else getattr(trip, k)) for k in FORM_FIELDS}
    return _form_page(request, values, [], trip_id)


@router.post("/trips/{trip_id}/edit", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def edit_trip(request: Request, trip_id: int, session: Session = Depends(get_session)):
    return await _save(request, session, _get_trip(session, trip_id))


@router.get("/trips/{trip_id}", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def trip_page(request: Request, trip_id: int, session: Session = Depends(get_session),
              hour_markup: Decimal = Query(Weights.hour_markup, ge=0, le=100),
              transfer_markup: Decimal = Query(Weights.transfer_markup, ge=0, le=100),
              airport_before_min: int = Query(Weights.airport_before_min, ge=0, le=1440),
              airport_after_min: int = Query(Weights.airport_after_min, ge=0, le=1440),
              baggage_fee: Decimal = Query(Weights.baggage_fee, ge=0, le=1000)) -> HTMLResponse:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    # subqueryload: one statement per relation; selectinload adds one per 500 offers (#115)
    itineraries = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.hidden.is_(False))
                                  .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = session.scalars(select(AccessTime)).all()  # once per request
    weights = Weights(hour_markup, transfer_markup, airport_before_min, airport_after_min, baggage_fee)  # the score is computed here and never stored
    rows = []
    for it in itineraries:
        if not it.fares:
            continue  # an itinerary with no fare has no cost: it is not a row
        fare = min(it.fares, key=lambda f: f.latest_price)
        cost = effective_cost(fare.latest_price, it.duration_min, it.transfers, weights,
                              door_extras(it, places, hour_markup) + flight_extras(it, weights))
        rows.append((it, fare, cost))
    rows.sort(key=lambda r: (r[2].total, r[0].depart_at))
    context = {"trip": trip, "rows": rows, "weights": weights, "format_breakdown": format_breakdown,
               "now": datetime.now(timezone.utc)}
    if request.headers.get("HX-Request"):  # a slider change: only the rows (htmx, #14)
        return templates.TemplateResponse(request, "trip_rows.html", context)
    return templates.TemplateResponse(request, "trip.html", context)


def _tokens_page(request: Request, session: Session, new_token: str | None = None, code: int = 200) -> HTMLResponse:
    tokens = session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())).all()
    server_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(request, "tokens.html", {"tokens": tokens, "new_token": new_token,
                                                               "server_url": server_url}, status_code=code)


@router.get("/tokens", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def tokens_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _tokens_page(request, session)


@router.post("/tokens", response_class=HTMLResponse, dependencies=[Depends(require_login), Depends(verify_csrf)])
def new_token(request: Request, name: str = Form(""), session: Session = Depends(get_session)) -> HTMLResponse:
    name = name.strip()[:100]
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a token needs a name")
    # The value shows only in this response; the database keeps only its hash (P5).
    return _tokens_page(request, session, create_token(session, name))


@router.post("/tokens/{token_id}/revoke", dependencies=[Depends(require_login), Depends(verify_csrf)])
def revoke(token_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    revoke_token(session, token_id)
    return RedirectResponse("/tokens", status_code=303)


PLACE_KINDS = ("access", "egress")


@router.get("/places", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def places_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    places = session.scalars(select(AccessTime).order_by(AccessTime.kind, AccessTime.place_text, AccessTime.id)).all()
    return templates.TemplateResponse(request, "places.html", {"places": places, "kinds": PLACE_KINDS})


@router.post("/places", dependencies=[Depends(require_login), Depends(verify_csrf)])
def new_place(place_text: str = Form(""), kind: str = Form(""), minutes: str = Form(""), cost: str = Form(""),
              session: Session = Depends(get_session)) -> RedirectResponse:
    place_text = place_text.strip()
    try:
        minutes_value = int(minutes)
        cost_value = Decimal(cost.strip() or "0")
    except (ValueError, InvalidOperation):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "minutes and cost must be numbers")
    if (not place_text or len(place_text) > 200 or kind not in PLACE_KINDS or minutes_value < 0
            or not cost_value.is_finite() or cost_value < 0 or cost_value >= Decimal("100000000")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a place needs a text, a kind and values >= 0")
    session.add(AccessTime(place_text=place_text, kind=kind, minutes=minutes_value,
                           cost=cost_value.quantize(Decimal("0.01"))))
    session.commit()
    return RedirectResponse("/places", status_code=303)


@router.post("/places/{place_id}/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_place(place_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    place = session.get(AccessTime, place_id)
    if place is not None:
        session.delete(place)
        session.commit()
    return RedirectResponse("/places", status_code=303)
