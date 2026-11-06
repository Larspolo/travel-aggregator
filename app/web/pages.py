"""The web pages: login, logout, the trips list, the trip page, the API tokens and the access and egress places and the settings. Jinja2 escapes all output: captured text is
untrusted (P5)."""

import dataclasses
import math
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from pydantic import Field, ValidationError
from sqlalchemy.orm import Session, subqueryload

from app.auth import SESSION_KEY, check_password, csrf_token, login_limiter, require_login, verify_csrf
from app.config import get_settings
from app.db import get_session
from app.door import door_extras, flight_extras
from app.flexibility import flexibility_extras
from app.history import chart
from app.risk import mode_extras, self_transfer_extras, transfer_extras
from app.profiles import active_weights, default_weights, delete as delete_profile, from_config, list_profiles
from app.profiles import rename as rename_profile, save as save_profile, set_default as set_default_profile, to_config
from app.models import AccessTime, ApiToken, Itinerary, ScoreProfile, Setting, Trip
from app.retention import MAX_RETENTION_DAYS, RETENTION_KEY, retention_days
from app.schemas import TripForm
from app.ranking import Weights, effective_cost, format_breakdown
from app.timeofday import night_extras, night_time_extras, time_extras
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


CLOCK_PATTERN = r"^(|([01]\d|2[0-3]):[0-5]\d)$"  # HH:MM, or empty for no limit (#181)


def in_time_window(it, earliest_depart: time | None, latest_arrive: time | None) -> bool:
    """True when the first leg departs at or after earliest_depart and the last leg arrives by latest_arrive (#181).

    The local times of the stored offsets decide. An arrival on a later day than the departure is after any limit.
    """
    first, last = it.legs[0], it.legs[-1]
    dep = (first.depart_at + timedelta(minutes=first.depart_offset_min)).replace(tzinfo=None)
    arr = (last.arrive_at + timedelta(minutes=last.arrive_offset_min)).replace(tzinfo=None)
    if earliest_depart is not None and dep.time() < earliest_depart:
        return False
    if latest_arrive is not None and (arr.date() > dep.date() or arr.time() > latest_arrive):
        return False
    return True


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
    address = request.client.host if request.client else "unknown"
    wait = login_limiter.retry_after(address)
    if wait:
        minutes = math.ceil(wait / 60)
        return HTMLResponse(f"Too many attempts. Try again in {minutes} minutes.", status_code=429,
                            headers={"Retry-After": str(wait)})
    if check_password(password, get_settings().owner_password_hash):
        login_limiter.success(address)
        request.session.clear()
        request.session[SESSION_KEY] = True
        csrf_token(request)  # a new token after the login
        return RedirectResponse("/", status_code=303)
    login_limiter.failure(address)
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


WEIGHT_NAMES = {f.name for f in dataclasses.fields(Weights)}  # the query parameters of the weights (#230)
SORT_KEYS = {  # the sort keys of the trip table columns (#112); None sorts as the empty text
    "route": lambda r: (r[0].legs[0].from_name or "", r[0].legs[-1].to_name or ""),
    "depart": lambda r: r[0].depart_at,
    "arrive": lambda r: r[0].arrive_at,
    "carrier": lambda r: [leg.carrier or "" for leg in r[0].legs],
    "fare": lambda r: (r[1].fare_name or "", r[1].source),
    "price": lambda r: r[1].latest_price,
    "cost": lambda r: r[2].total,
}


@router.get("/trips/{trip_id}", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def trip_page(request: Request, trip_id: int, session: Session = Depends(get_session),
              hour_markup: Decimal | None = Query(None, ge=0, le=100),
              transfer_markup: Decimal | None = Query(None, ge=0, le=100),
              airport_before_min: int | None = Query(None, ge=0, le=1440),
              airport_after_min: int | None = Query(None, ge=0, le=1440),
              baggage_fee: Decimal | None = Query(None, ge=0, le=1000),
              early_limit: time | None = Query(None),
              late_limit: time | None = Query(None),
              time_window_penalty: Decimal | None = Query(None, ge=0, le=1000),
              night_start: time | None = Query(None), night_end: time | None = Query(None),
              night_min: int | None = Query(None, ge=0, le=1440),
              night_adjust: Decimal | None = Query(None, ge=-1000, le=1000),
              night_hour_markup: Decimal | None = Query(None, ge=0, le=100),
              short_transfer_min: int | None = Query(None, ge=0, le=240),
              short_transfer_penalty: Decimal | None = Query(None, ge=0, le=1000),
              flex_non_refundable: Decimal | None = Query(None, ge=-1000, le=1000),
              flex_partly_refundable: Decimal | None = Query(None, ge=-1000, le=1000),
              flex_flexible: Decimal | None = Query(None, ge=-1000, le=1000),
              self_transfer_penalty: Decimal | None = Query(None, ge=0, le=1000),
              stale_hours: int | None = Query(None, ge=1, le=720),
              sort: str = Query("cost", pattern="^(" + "|".join(SORT_KEYS) + ")$"),
              dir: str = Query("asc", pattern="^(asc|desc)$"),
              mode: str = Query("", max_length=50), source: str = Query("", max_length=50),
              train_markup: Decimal | None = Query(None, ge=-1000, le=1000),
              bus_markup: Decimal | None = Query(None, ge=-1000, le=1000),
              flight_markup: Decimal | None = Query(None, ge=-1000, le=1000),
              ferry_markup: Decimal | None = Query(None, ge=-1000, le=1000),
              max_transfers: str = Query("", max_length=5), max_duration_min: str = Query("", max_length=6),
              earliest_depart: str = Query("", pattern=CLOCK_PATTERN), latest_arrive: str = Query("", pattern=CLOCK_PATTERN),
              exclude_mode: list[Annotated[str, Field(max_length=50)]] = Query([]),
              exclude_carrier: list[Annotated[str, Field(max_length=50)]] = Query([]),
              show_hidden: bool = Query(False), hide_stale: bool = Query(False)) -> HTMLResponse:
    # the weights of the URL; None = not in the URL, the default profile gives the value (#230)
    overrides = {k: v for k, v in locals().items() if k in WEIGHT_NAMES}
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    # an empty box of the form is no limit (#180); a number is capped to its range
    limit_transfers = min(int(max_transfers), 10) if max_transfers.isdigit() else None
    limit_duration = min(int(max_duration_min), 10080) if max_duration_min.isdigit() else None
    # an empty box is no limit (#181); the pattern admits only HH:MM
    limit_depart = time.fromisoformat(earliest_depart) if earliest_depart else None
    limit_arrive = time.fromisoformat(latest_arrive) if latest_arrive else None
    # subqueryload: one statement per relation; selectinload adds one per 500 offers (#115)
    hidden_filter = [] if show_hidden else [Itinerary.hidden.is_(False)]  # "show hidden" (#200)
    itineraries = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, *hidden_filter)
                                  .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = session.scalars(select(AccessTime)).all()  # once per request
    weights = active_weights(default_weights(session), overrides)  # the score is computed here and never stored
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(hours=weights.stale_hours)  # a row older than this is stale (#275)
    rows, modes, sources, carriers = [], set(), set(), set()
    for it in itineraries:
        if not it.fares:
            continue  # an itinerary with no fare has no cost: it is not a row
        it_modes = {m for m in (it.mode_summary or "").split("+") if m}
        modes |= it_modes
        sources |= {f.source for f in it.fares}
        carriers |= {leg.carrier for leg in it.legs if leg.carrier}
        fares = [f for f in it.fares if not source or f.source == source]
        if not fares or (mode and mode not in it_modes):
            continue  # the filter hides this row (#112)
        if (limit_transfers is not None and it.transfers > limit_transfers) or (
                limit_duration is not None and it.duration_min > limit_duration):
            continue  # the limits of transfers and duration hide this row
        if any(leg.mode in exclude_mode or leg.carrier in exclude_carrier for leg in it.legs):
            continue  # an excluded mode or carrier hides each offer with one of its legs
        if it.legs and not in_time_window(it, limit_depart, limit_arrive):
            continue  # the time limits hide this row (#181)
        if hide_stale and max(f.latest_captured_at for f in it.fares) < stale_before:
            continue  # "hide stale" hides a row whose newest capture is stale (#277)
        base = (door_extras(it, places, weights.hour_markup) + flight_extras(it, weights) + time_extras(it, weights)
                + night_extras(it, weights) + night_time_extras(it, weights) + mode_extras(it, weights)
                + transfer_extras(it, weights))
        # the main fare has the lowest effective cost; a tie goes to the lowest price (#175)
        fare, cost = min(((f, effective_cost(f.latest_price, it.duration_min, it.transfers, weights,
                                             base + flexibility_extras(f, weights) + self_transfer_extras(f, weights)))
                          for f in fares), key=lambda fc: (fc[1].total, fc[0].latest_price))
        rows.append((it, fare, cost))
    rows.sort(key=lambda r: (r[2].total, r[0].depart_at))  # the default order and the tie order
    badges = {}  # the highlights of the filtered rows (#113); a tie goes to the first row in the default order
    shown = [r for r in rows if not r[0].hidden]  # a hidden row gets no highlight (#200)
    if shown:
        for name, key in (("best value", lambda r: r[2].total), ("cheapest", lambda r: r[1].latest_price),
                          ("fastest", lambda r: r[0].duration_min)):
            badges.setdefault(min(shown, key=key)[0].id, []).append(name)
    if sort != "cost" or dir == "desc":
        rows.sort(key=SORT_KEYS[sort], reverse=dir == "desc")
    rows.sort(key=lambda r: not r[0].pinned)  # stable: the pinned rows first in every order, in their order (#199)
    view = {"sort": sort, "dir": dir, "mode": mode, "source": source, "badges": badges, "show_hidden": show_hidden,
            "max_transfers": limit_transfers, "max_duration_min": limit_duration,
            "earliest_depart": earliest_depart, "latest_arrive": latest_arrive,
            "modes": sorted(modes), "sources": sorted(sources), "carriers": sorted(carriers),
            "exclude_mode": exclude_mode, "exclude_carrier": exclude_carrier, "hide_stale": hide_stale}
    # the active weights (#230): a slider change or a sort keeps all values; night_hour_markup None is not sent
    query = {**{k: v for k, v in to_config(weights).items() if v is not None}, "mode": mode, "source": source,
             **({"max_transfers": limit_transfers} if limit_transfers is not None else {}),
             **({"max_duration_min": limit_duration} if limit_duration is not None else {}),
             **({"earliest_depart": earliest_depart} if limit_depart is not None else {}),
             **({"latest_arrive": latest_arrive} if limit_arrive is not None else {}),
             "exclude_mode": exclude_mode, "exclude_carrier": exclude_carrier}
    if show_hidden:
        query["show_hidden"] = True  # the sort links and the sliders keep it (#200)
    if hide_stale:
        query["hide_stale"] = True  # the sort links keep it (#277)
    context = {"trip": trip, "rows": rows, "weights": weights, "view": view, "sort_query": query, "sort_qs": urlencode(query, doseq=True), "format_breakdown": format_breakdown,
               "now": now, "stale_before": stale_before}
    if request.headers.get("HX-Request"):  # a slider change: only the rows (htmx, #14)
        return templates.TemplateResponse(request, "trip_table.html", context)
    return templates.TemplateResponse(request, "trip.html", context)


def _tokens_page(request: Request, session: Session, new_token: str | None = None, code: int = 200) -> HTMLResponse:
    tokens = session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())).all()
    server_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(request, "tokens.html", {"tokens": tokens, "new_token": new_token,
                                                               "server_url": server_url}, status_code=code)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/pin",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_pin(trip_id: int, itinerary_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.pinned = not it.pinned
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/profiles", dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_profile_page(trip_id: int = Form(...), name: str = Form(..., min_length=1, max_length=100),
                      hour_markup: Decimal = Form(Weights.hour_markup, ge=0, le=100),
                      transfer_markup: Decimal = Form(Weights.transfer_markup, ge=0, le=100),
                      airport_before_min: int = Form(Weights.airport_before_min, ge=0, le=1440),
                      airport_after_min: int = Form(Weights.airport_after_min, ge=0, le=1440),
                      baggage_fee: Decimal = Form(Weights.baggage_fee, ge=0, le=1000),
                      early_limit: time = Form(Weights.early_limit), late_limit: time = Form(Weights.late_limit),
                      time_window_penalty: Decimal = Form(Weights.time_window_penalty, ge=0, le=1000),
                      night_start: time = Form(Weights.night_start), night_end: time = Form(Weights.night_end),
                      night_min: int = Form(Weights.night_min, ge=0, le=1440),
                      night_adjust: Decimal = Form(Weights.night_adjust, ge=-1000, le=1000),
                      night_hour_markup: Decimal | None = Form(None, ge=0, le=100),
                      short_transfer_min: int = Form(Weights.short_transfer_min, ge=0, le=240),
                      short_transfer_penalty: Decimal = Form(Weights.short_transfer_penalty, ge=0, le=1000),
                      train_markup: Decimal = Form(Weights.train_markup, ge=-1000, le=1000),
                      bus_markup: Decimal = Form(Weights.bus_markup, ge=-1000, le=1000),
                      flight_markup: Decimal = Form(Weights.flight_markup, ge=-1000, le=1000),
                      ferry_markup: Decimal = Form(Weights.ferry_markup, ge=-1000, le=1000),
                      flex_non_refundable: Decimal = Form(Weights.flex_non_refundable, ge=-1000, le=1000),
                      flex_partly_refundable: Decimal = Form(Weights.flex_partly_refundable, ge=-1000, le=1000),
                      flex_flexible: Decimal = Form(Weights.flex_flexible, ge=-1000, le=1000),
                      self_transfer_penalty: Decimal = Form(Weights.self_transfer_penalty, ge=0, le=1000),
                      stale_hours: int = Form(Weights.stale_hours, ge=1, le=720),
                      session: Session = Depends(get_session)) -> RedirectResponse:
    """Store the present weights of the trip page as a named profile (#229); the same ranges as `trip_page`."""
    if session.get(Trip, trip_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    weights = Weights(hour_markup=hour_markup, transfer_markup=transfer_markup,
                      airport_before_min=airport_before_min, airport_after_min=airport_after_min,
                      baggage_fee=baggage_fee, early_limit=early_limit, late_limit=late_limit,
                      time_window_penalty=time_window_penalty, night_start=night_start, night_end=night_end,
                      night_min=night_min, night_adjust=night_adjust, night_hour_markup=night_hour_markup,
                      short_transfer_min=short_transfer_min, short_transfer_penalty=short_transfer_penalty,
                      train_markup=train_markup, bus_markup=bus_markup, flight_markup=flight_markup,
                      ferry_markup=ferry_markup, flex_non_refundable=flex_non_refundable,
                      flex_partly_refundable=flex_partly_refundable, flex_flexible=flex_flexible,
                      self_transfer_penalty=self_transfer_penalty, stale_hours=stale_hours)
    save_profile(session, name.strip(), weights)
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


def _profiles_page(request: Request, session: Session, error: str | None = None, code: int = 200) -> HTMLResponse:
    rows = [(p, from_config(p.config_json)) for p in list_profiles(session)]
    return templates.TemplateResponse(request, "profiles.html", {"rows": rows, "error": error}, status_code=code)


@router.get("/profiles", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def profiles_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _profiles_page(request, session)


@router.post("/profiles/{profile_id}/default", dependencies=[Depends(require_login), Depends(verify_csrf)])
def set_default_profile_page(profile_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    if not set_default_profile(session, profile_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    return RedirectResponse("/profiles", status_code=303)


@router.post("/profiles/{profile_id}/rename", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def rename_profile_page(profile_id: int, request: Request, name: str = Form(""),
                        session: Session = Depends(get_session)):
    name = name.strip()
    if session.get(ScoreProfile, profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    if not name or len(name) > 100:
        return _profiles_page(request, session, "A name needs 1 to 100 characters; nothing changed.", 422)
    if not rename_profile(session, profile_id, name):
        return _profiles_page(request, session, f'The name "{name}" exists already; nothing changed.', 422)
    return RedirectResponse("/profiles", status_code=303)


@router.post("/profiles/{profile_id}/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_profile_page(profile_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    if not delete_profile(session, profile_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    return RedirectResponse("/profiles", status_code=303)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/booked",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_booked(trip_id: int, itinerary_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.booked = not it.booked
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/note",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_note(trip_id: int, itinerary_id: int, note: str = Form("", max_length=2000),
              session: Session = Depends(get_session)) -> RedirectResponse:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.note = note.strip() or None
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.get("/trips/{trip_id}/itineraries/{itinerary_id}/history", response_class=HTMLResponse,
            dependencies=[Depends(require_login)])
def price_history(trip_id: int, itinerary_id: int, request: Request,
                  session: Session = Depends(get_session)) -> HTMLResponse:
    """The price history of each fare of an itinerary, the newest capture first (#240): a fragment, no page."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    return templates.TemplateResponse(request, "price_history.html",
                                      {"fares": it.fares, "chart": chart(it.fares)})


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/hide",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_hide(trip_id: int, itinerary_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.hidden = not it.hidden
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


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


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def settings_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", {"retention_days": retention_days(session),
                                                                 "max_days": MAX_RETENTION_DAYS})


@router.post("/settings", dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_settings(retention: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    value = retention.strip()
    if not value.isdigit() or int(value) > MAX_RETENTION_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"the retention period must be a whole number from 0 to {MAX_RETENTION_DAYS}")
    session.merge(Setting(key=RETENTION_KEY, value=str(int(value))))
    session.commit()
    return RedirectResponse("/settings", status_code=303)
