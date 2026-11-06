"""The web pages: login, logout, the trips list and the trip page. Jinja2 escapes all output: captured text is
untrusted (P5)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.auth import SESSION_KEY, check_password, csrf_token, require_login, verify_csrf
from app.config import get_settings
from app.db import get_session
from app.models import Itinerary, Trip
from app.schemas import TripForm
from app.trips import list_trips

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["csrf_token"] = csrf_token


def local(t: datetime, offset_min: int) -> datetime:
    """The time as the travel site showed it: UTC back to its original offset."""
    return t.astimezone(timezone(timedelta(minutes=offset_min)))


templates.env.filters["local"] = local


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
def trip_page(request: Request, trip_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    itineraries = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.hidden.is_(False))
                                  .options(selectinload(Itinerary.legs), selectinload(Itinerary.fares))).all()
    rows = [(it, min(it.fares, key=lambda f: f.latest_price)) for it in itineraries if it.fares]
    rows.sort(key=lambda r: (r[1].latest_price, r[0].depart_at))   # ranking comes with rank:base
    return templates.TemplateResponse(request, "trip.html", {"trip": trip, "rows": rows})
