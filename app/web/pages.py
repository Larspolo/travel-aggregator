"""The web pages: login, logout, the start page and the trip page. Jinja2 escapes all output: captured text is
untrusted (P5)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import SESSION_KEY, check_password, csrf_token, require_login, verify_csrf
from app.config import get_settings
from app.db import get_session
from app.models import Itinerary, Trip

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
def index() -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><title>travel-aggregator</title><h1>travel-aggregator</h1>"
        '<p><a href="/logout">Log out</a></p>'
    )


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
