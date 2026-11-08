"""The web pages: login, logout, the trips list, the trip page, the API tokens and the access and egress places and the settings. Jinja2 escapes all output: captured text is
untrusted (P5)."""

import dataclasses
import inspect
import math
import os
import re
from datetime import datetime, time, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, subqueryload

from app.web.userscripts import bundle_info, userscript_list
from app.auth import SESSION_KEY, check_password, csrf_token, login_limiter, require_login, verify_csrf
from app.backup import newest_backup
from app.config import get_settings
from app.currency import by_eur, load_rates, to_eur
from app.days import day_summary
from app.timeline import timeline
from app.db import get_session
from app.target import at_target
from app.drops import drops_by_trip, mark_seen, trip_drops
from app.door import door_extras, flight_extras
from app.flexibility import flexibility_extras
from app.travelclass import class_extras
from app.tradeoff import break_even
from app.history import chart, trend_chart
from app.trend import trip_trend
from app.money import money
from app.coverage import trip_coverage
from app.sourcehealth import failing_sources
from app.risk import mode_extras, self_transfer_extras, stale_extras, transfer_extras
from app.profiles import active_weights, default_weights, delete as delete_profile, from_config, list_profiles
from app.profiles import rename as rename_profile, save as save_profile, set_default as set_default_profile, to_config
from app.profiles import update_weights as update_profile
from app.models import AccessTime, ApiToken, Capture, CurrencyRate, FarePrice, Itinerary, PushSubscription, ScoreProfile, Setting, Trip
from app.notify import (CHANNEL_KEY, CHANNELS, EMAIL_KEY, NTFY_URL_KEY, alert_messages, deliver, setting,
                        webpush_ready)
from app.retention import MAX_RETENTION_DAYS, RETENTION_KEY, retention_days
from app.schemas import TripForm
from app.parsers import group_price
from app.ranking import (Weights, _amount, bar_parts, effective_cost, for_group, format_breakdown, format_total, in_eur,
                         per_traveler)
from app.timeofday import night_extras, night_time_extras, time_extras
from app.tokens import create as create_token, revoke as revoke_token
from app.trips import archived_journeys, chain, list_trips

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["csrf_token"] = csrf_token
# All settings pages, in groups: the settings navigation of each settings page and the "Settings" link of the
# app bar use this one list (#925, DESIGN.md section 5, "Settings").
SETTINGS_NAV = [
    ("App", [("/settings", "General", "settings"), ("/settings/messages", "Messages", "chart")]),
    ("Ranking", [("/profiles", "Profiles", "user"), ("/places", "Places", "map-pin"),
                 ("/rates", "Exchange rates", "arrow-right-left")]),
    ("Capture", [("/tokens", "Userscripts", "key"), ("/sources/new", "Add a website", "plus")]),
]
SETTINGS_PATHS = [href for _, items in SETTINGS_NAV for href, _, _ in items]
templates.env.globals["settings_nav"] = SETTINGS_NAV
templates.env.globals["settings_paths"] = SETTINGS_PATHS


def local(t: datetime, offset_min: int) -> datetime:
    """The time as the travel site showed it: UTC back to its original offset."""
    return t.astimezone(timezone(timedelta(minutes=offset_min)))


templates.env.filters["local"] = local

MODE_ICONS = {"train": "train", "bus": "bus", "flight": "plane", "walk": "walk"}


def mode_icon(mode: str) -> str:
    """The name of the icon in static/icons.svg of one leg mode ("" for a mode with no icon)."""
    return MODE_ICONS.get(mode, "")


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


def depart_day(it) -> str:
    """The local date (YYYY-MM-DD) of the first leg's departure, as the stored offset gives it (#709)."""
    first = it.legs[0]
    return (first.depart_at + timedelta(minutes=first.depart_offset_min)).date().isoformat()


def ago(t: datetime, now: datetime) -> str:
    """The age of a capture, for example '2 h ago'."""
    seconds = max(0, int((now - t).total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 48 * 3600:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} days ago"


templates.env.filters["money"] = money
templates.env.filters["mode_icon"] = mode_icon
templates.env.filters["day_gap"] = day_gap
templates.env.filters["ago"] = ago
templates.env.filters["by_eur"] = by_eur


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
def index(request: Request, archived: bool = False, session: Session = Depends(get_session)) -> HTMLResponse:
    rows = list_trips(session)
    archived_count = sum(1 for kind, _, _ in archived_journeys(rows, True) if kind == "trip")
    return templates.TemplateResponse(request, "trips.html",
                                      {"lines": archived_journeys(rows, archived), "drops": drops_by_trip(session),
                                       "archived": archived, "archived_count": archived_count,
                                       "failing": failing_sources(session)})


FORM_FIELDS = tuple(TripForm.model_fields)


def _form_page(request: Request, values: dict, errors: list[str], trip_id: int | None, session: Session,
               code: int = 200):
    journey = len(chain(_get_trip(session, trip_id))) if trip_id else 1  # the button "Copy journey" (#802)
    return templates.TemplateResponse(request, "trip_form.html",
                                      {"values": values, "errors": errors, "trip_id": trip_id, "journey": journey,
                                       "profiles": list_profiles(session)}, status_code=code)


async def _save(request: Request, session: Session, trip: Trip | None):
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FORM_FIELDS}
    try:
        data = TripForm.model_validate(values)
    except ValidationError as e:
        errors = [f"{'.'.join(map(str, err['loc'])) or 'form'}: {err['msg']}" for err in e.errors()]
        return _form_page(request, values, errors, trip.id if trip else None, session, 422)
    if data.profile_id is not None and session.get(ScoreProfile, data.profile_id) is None:
        return _form_page(request, values, [f"profile_id: no profile {data.profile_id}"], trip.id if trip else None,
                          session, 422)
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
def new_trip_form(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _form_page(request, {"travelers": 1, "status": "planning"}, [], None, session)


@router.post("/trips/new", response_class=HTMLResponse, dependencies=[Depends(require_login), Depends(verify_csrf)])
async def new_trip(request: Request, session: Session = Depends(get_session)):
    return await _save(request, session, None)


@router.get("/trips/{trip_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def edit_trip_form(request: Request, trip_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    values = {k: ("" if getattr(trip, k) is None else getattr(trip, k)) for k in FORM_FIELDS}
    return _form_page(request, values, [], trip_id, session)


@router.post("/trips/{trip_id}/edit", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def edit_trip(request: Request, trip_id: int, session: Session = Depends(get_session)):
    return await _save(request, session, _get_trip(session, trip_id))


@router.get("/trips/{trip_id}/delete", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def delete_trip_confirm(request: Request, trip_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    counts = {"itineraries": session.scalar(select(func.count(Itinerary.id)).where(Itinerary.trip_id == trip_id)),
              "captures": session.scalar(select(func.count(Capture.id)).where(Capture.trip_id == trip_id))}
    return templates.TemplateResponse(request, "trip_delete.html", {"trip": trip, "counts": counts})


@router.post("/trips/{trip_id}/delete", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_trip_page(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    # The database deletes the offers, prices and captures (CASCADE); a return trip keeps, unlinked (SET NULL).
    # A middle trip of a journey: its next trip links to its previous trip (#563). The column is unique, so the
    # link of this trip goes first.
    trip = _get_trip(session, trip_id)
    previous_id = trip.return_of_id
    following = session.scalar(select(Trip).where(Trip.return_of_id == trip.id))
    if previous_id is not None and following is not None:
        trip.return_of_id = None
        session.flush()
        following.return_of_id = previous_id
        session.flush()
    session.delete(trip)
    session.commit()
    return RedirectResponse("/", status_code=303)


WEIGHT_NAMES = {f.name for f in dataclasses.fields(Weights)}  # the query parameters of the weights (#230)
SORT_KEYS = {  # the sort keys of the trip table columns (#112); None sorts as the empty text
    "route": lambda r: (r[0].legs[0].from_name or "", r[0].legs[-1].to_name or ""),
    "depart": lambda r: r[0].depart_at,
    "arrive": lambda r: r[0].arrive_at,
    "carrier": lambda r: [leg.carrier or "" for leg in r[0].legs],
    "fare": lambda r: (r[1].fare_name or "", r[1].source),
    "price": lambda r: r[2].price,  # the EUR value (#385)
    "cost": lambda r: r[2].total,
}


def weight_query(hour_markup: Decimal | None = Query(None, ge=0, le=100),
                 transfer_markup: Decimal | None = Query(None, ge=0, le=100),
                 airport_before_min: int | None = Query(None, ge=0, le=1440),
                 airport_after_min: int | None = Query(None, ge=0, le=1440),
                 baggage_fee: Decimal | None = Query(None, ge=0, le=1000),
                 early_limit: time | None = Query(None),
                 late_limit: time | None = Query(None),
                 time_window_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 night_start: time | None = Query(None),
                 night_end: time | None = Query(None),
                 night_min: int | None = Query(None, ge=0, le=1440),
                 night_adjust: Decimal | None = Query(None, ge=-1000, le=1000),
                 night_hour_markup: Decimal | None = Query(None, ge=0, le=100),
                 short_transfer_min: int | None = Query(None, ge=0, le=240),
                 short_transfer_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 flex_non_refundable: Decimal | None = Query(None, ge=-1000, le=1000),
                 flex_partly_refundable: Decimal | None = Query(None, ge=-1000, le=1000),
                 flex_flexible: Decimal | None = Query(None, ge=-1000, le=1000),
                 first_class_hour: Decimal | None = Query(None, ge=-1000, le=1000),
                 self_transfer_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 stale_hours: int | None = Query(None, ge=1, le=720),
                 stale_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 train_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 bus_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 flight_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 ferry_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 hour_tier1_after_min: int | None = Query(None, ge=0, le=2880),
                 hour_tier1_markup: Decimal | None = Query(None, ge=0, le=100),
                 hour_tier2_after_min: int | None = Query(None, ge=0, le=2880),
                 hour_tier2_markup: Decimal | None = Query(None, ge=0, le=100)) -> dict:
    """The weights of the URL; None = not in the URL, the profile gives the value (#230)."""
    return dict(locals())


def resolve_weights(session: Session, trip: Trip, overrides: dict, profile: int | None):
    """The active weights and the chosen profile (#232): a weight in the URL, the profile of the URL (#231), the
    profile of the trip, the default one. An unknown id in the URL gives the default profile, no error."""
    if profile is not None:
        chosen = session.get(ScoreProfile, profile)
    else:
        chosen = session.get(ScoreProfile, trip.profile_id) if trip.profile_id is not None else None
    base = from_config(chosen.config_json) if chosen is not None else default_weights(session)
    return active_weights(base, overrides), chosen  # the score is computed here and never stored


def fare_travelers(session: Session, itineraries) -> dict[int, int]:
    """The travelers of the newest price of each fare whose source gives the price of the group (#767): the fare id to
    `Capture.travelers` of that price. Only counts of 2 or more: 1, no count or no capture keep the price."""
    sources = {f.source for it in itineraries for f in it.fares}
    ids = [f.id for it in itineraries for f in it.fares if f.source in {s for s in sources if group_price(s)}]
    if not ids:
        return {}
    rows = session.execute(select(FarePrice.fare_id, Capture.travelers)
                           .outerjoin(Capture, FarePrice.capture_id == Capture.id)
                           .where(FarePrice.fare_id.in_(ids))
                           .order_by(FarePrice.captured_at, FarePrice.id)).all()
    newest = dict(rows)  # the last row of each fare is its newest price
    return {fare_id: n for fare_id, n in newest.items() if n is not None and n > 1}


def row_cost(it: Itinerary, fares, places, weights: Weights, stale_before: datetime, rates=None, counts=None):
    """The main fare of one itinerary and its effective cost: the lowest cost, a tie goes to the lowest price (#175).
    The cost uses the EUR value of the price (`rates` of `load_rates()`, #385); a fare with no rate comes last.
    The price part is per traveler (`counts` of `fare_travelers()`, #767); the other parts are per person."""
    rates, counts = rates or {}, counts or {}
    base = (door_extras(it, places, weights.hour_markup) + flight_extras(it, weights) + time_extras(it, weights)
            + night_extras(it, weights) + night_time_extras(it, weights) + mode_extras(it, weights)
            + transfer_extras(it, weights) + stale_extras(it, weights, stale_before))
    def cost(f):
        eur, n = to_eur(f.latest_price, f.currency, rates), counts.get(f.id)
        b = effective_cost(per_traveler(eur, n) if eur is not None else Decimal(0), it.duration_min, it.transfers, weights,
                           base + flexibility_extras(f, weights) + class_extras(f, it.duration_min, weights)
                               + self_transfer_extras(f, weights))
        return for_group(in_eur(b, f.latest_price, f.currency, eur), f.latest_price, f.currency, n)
    return min(((f, cost(f)) for f in fares), key=lambda fc: (fc[1].total, fc[1].price))


def _chosen_offer(session: Session, trip: Trip, weights: Weights, places, now: datetime):
    """The chosen offer of one direction (#342): booked, else pinned, else any; the lowest effective cost in the group.
    Hidden offers never count. None when the direction has no visible offer with a fare."""
    stale_before = now - timedelta(hours=weights.stale_hours)
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False))
                          .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    rates = load_rates(session)
    counts = fare_travelers(session, its)
    rows = [(it, *row_cost(it, it.fares, places, weights, stale_before, rates, counts)) for it in its if it.fares]
    if not rows:
        return None
    return min(rows, key=lambda r: (not r[0].booked, not r[0].pinned, r[2].total, r[0].depart_at))


def best_offer(session: Session, trip: Trip):
    """The best offer of the trip for the ingest response (#880): the lowest effective cost of the visible itineraries
    with fares, by the profile of the trip (else the default); a tie goes to the lowest departure.
    Returns (itinerary, fare, cost) or None."""
    weights, _ = resolve_weights(session, trip, {}, None)
    stale_before = datetime.now(timezone.utc) - timedelta(hours=weights.stale_hours)
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False))
                          .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = session.scalars(select(AccessTime)).all()
    rates = load_rates(session)
    counts = fare_travelers(session, its)
    rows = [(it, *row_cost(it, it.fares, places, weights, stale_before, rates, counts)) for it in its if it.fares]
    if not rows:
        return None
    return min(rows, key=lambda r: (r[2].total, r[0].depart_at))


def journey(session: Session, trip: Trip, weights: Weights, places, now: datetime):
    """The journey box (#342, #562): the chosen offer of each part of the chain and the total effective cost, or None
    when the trip has no link. The present part uses the page weights; the other parts their own profile."""
    parts = chain(trip)
    if len(parts) < 2:
        return None
    rows = []
    for t in parts:
        w = weights if t.id == trip.id else resolve_weights(session, t, {}, None)[0]
        rows.append((t, _chosen_offer(session, t, w, places, now)))
    labels = ["Outbound", "Return"] if len(parts) == 2 else [f"Part {i}" for i in range(1, len(parts) + 1)]
    directions, early_any = [], False
    for i, (t, chosen) in enumerate(rows):
        prev = rows[i - 1][1] if i else None
        early = bool(prev and chosen and chosen[0].depart_at < prev[0].arrive_at)
        early_any = early_any or early
        directions.append((labels[i], t, chosen, early))
    total = None
    if all(chosen is not None for _, chosen in rows):
        total = sum((chosen[2].total for _, chosen in rows), Decimal(0))
        total = total if total.is_finite() else None  # a fare with no rate has no cost (#385)
    return {"directions": directions, "total": total, "early": early_any and len(parts) == 2}


@router.get("/trips/{trip_id}", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def trip_page(request: Request, trip_id: int, session: Session = Depends(get_session),
              overrides: dict = Depends(weight_query),
              sort: str = Query("cost", pattern="^(" + "|".join(SORT_KEYS) + ")$"),
              dir: str = Query("asc", pattern="^(asc|desc)$"),
              mode: str = Query("", max_length=50),
              source: str = Query("", max_length=50),
              max_transfers: str = Query("", max_length=5),
              max_duration_min: str = Query("", max_length=6),
              earliest_depart: str = Query("", pattern=CLOCK_PATTERN),
              latest_arrive: str = Query("", pattern=CLOCK_PATTERN),
              day: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
              exclude_mode: list[Annotated[str, Field(max_length=50)]] = Query([]),
              exclude_carrier: list[Annotated[str, Field(max_length=50)]] = Query([]),
              show_hidden: bool = Query(False),
              hide_stale: bool = Query(False),
              profile: int | None = Query(None)) -> HTMLResponse:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    weights, chosen = resolve_weights(session, trip, overrides, profile)
    profiles = list_profiles(session)
    active_id = chosen.id if chosen is not None else next((p.id for p in profiles if p.is_default), None)
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
    rates = load_rates(session)  # once per request (#385)
    counts = fare_travelers(session, itineraries)  # once per request (#767)
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(hours=weights.stale_hours)  # a row older than this is stale (#275)
    rows, all_rows, modes, sources, carriers = [], [], set(), set(), set()
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
        fare, cost = row_cost(it, fares, places, weights, stale_before, rates, counts)
        all_rows.append((it, fare, cost))  # before the day filter: the days show all offers (#710)
        if day and it.legs and depart_day(it) != day:
            continue  # the day filter shows only the offers that depart on that local day (#709)
        rows.append((it, fare, cost))
    rows.sort(key=lambda r: (r[2].total, r[0].depart_at))  # the default order and the tie order
    badges = {}  # the highlights of the filtered rows (#113); a tie goes to the first row in the default order
    shown = [r for r in rows if not r[0].hidden]  # a hidden row gets no highlight (#200)
    if shown:
        for name, key in (("best value", lambda r: r[2].total), ("cheapest", lambda r: r[2].price),
                          ("fastest", lambda r: r[0].duration_min)):
            badges.setdefault(min(shown, key=key)[0].id, []).append(name)
    if sort != "cost" or dir == "desc":
        rows.sort(key=SORT_KEYS[sort], reverse=dir == "desc")
    rows.sort(key=lambda r: not r[0].pinned)  # stable: the pinned rows first in every order, in their order (#199)
    view = {"sort": sort, "dir": dir, "mode": mode, "source": source, "badges": badges, "show_hidden": show_hidden,
            "max_transfers": limit_transfers, "max_duration_min": limit_duration,
            "earliest_depart": earliest_depart, "latest_arrive": latest_arrive, "day": day,
            "modes": sorted(modes), "sources": sorted(sources), "carriers": sorted(carriers),
            "exclude_mode": exclude_mode, "exclude_carrier": exclude_carrier, "hide_stale": hide_stale}
    # the active weights (#230): a slider change or a sort keeps all values; night_hour_markup None is not sent
    query = {**{k: v for k, v in to_config(weights).items() if v is not None}, "mode": mode, "source": source,
             **({"max_transfers": limit_transfers} if limit_transfers is not None else {}),
             **({"max_duration_min": limit_duration} if limit_duration is not None else {}),
             **({"earliest_depart": earliest_depart} if limit_depart is not None else {}),
             **({"latest_arrive": latest_arrive} if limit_arrive is not None else {}),
             **({"day": day} if day else {}),
             "exclude_mode": exclude_mode, "exclude_carrier": exclude_carrier}
    if show_hidden:
        query["show_hidden"] = True  # the sort links and the sliders keep it (#200)
    if hide_stale:
        query["hide_stale"] = True  # the sort links keep it (#277)
    if chosen is not None:
        query["profile"] = chosen.id  # a slider change or a sort keeps the profile (#231)
    # the break-even links re-rank this page with another hour value: the sort and the filters stay (#920)
    tradeoff = tradeoff_lines(rows, shown, source, places, weights, stale_before, rates,
                              trip_id, {**query, "sort": sort, "dir": dir}, counts)  # #895
    context = {"trip": trip, "rows": rows, "weights": weights, "view": view, "sort_query": query, "sort_qs": urlencode(query, doseq=True), "format_breakdown": format_breakdown,
               "format_total": format_total, "bar_parts": bar_parts,
               "now": now, "stale_before": stale_before, "profiles": profiles, "active_profile_id": active_id,
               "rates": rates, "tradeoff": tradeoff,
               "new_since": trip.viewed_at}  # the rows after the last full view are "new" (#1090)
    context["days"] = day_summary(all_rows, trip.date_from, trip.date_to,
                                  lambda it: depart_day(it) if it.legs else None)  # the days (#710)
    # the timeline of the shown rows (#815): one block per departure day; a bar links to its row
    context["timeline"] = timeline(rows, lambda it: depart_day(it) if it.legs else None)
    context["timeline_rows"] = {r[0].id: r for r in rows}
    # the links of the days strip (#711): all values of the query but the day
    context["days_qs"] = urlencode({k: v for k, v in query.items() if k != "day"}, doseq=True)
    # the seen price of each shown fare before mark_seen() changes it: the price changes of the rows (#1092)
    context["seen"] = {f.id: f.seen_price for r in rows for f in r[0].fares}
    if request.headers.get("HX-Request"):  # a slider change: only the rows (htmx, #14)
        return templates.TemplateResponse(request, "trip_table.html", context)
    context["drops"] = trip_drops(session, trip_id)  # the drops since the last full view (#355)
    trend = trip_trend(session, trip_id)  # the cheapest price per day (#851): a chart for 2 or more days
    context["trend"] = trend_chart(trend) if len(trend) >= 2 else None
    context["at_target"] = at_target(session, trip)  # the fares at or below the target price (#847)
    mark_seen(session, trip_id)
    trip.viewed_at = now  # only the full view; an HX-Request keeps it (#1090)
    session.commit()
    context["journey"] = journey(session, trip, weights, places, now)
    context["coverage"] = trip_coverage(session, trip)  # the search status and link per source (#318, #967)
    context["flash"] = request.session.pop("flash", None)
    context["share_link"] = request.session.pop("share_link", None)  # once after "Share" (#903)  # a message of the last action, for example an import
    return templates.TemplateResponse(request, "trip.html", context)


def trip_view(**params) -> dict:
    """The query values of the trip page (sort, filters, weights) for a POST of a row action (#666)."""
    return params


trip_view.__signature__ = inspect.signature(trip_page).replace(parameters=[
    p for name, p in inspect.signature(trip_page).parameters.items() if name not in ("request", "trip_id", "session")])


def _rows_or_redirect(request: Request, trip_id: int, session: Session, view: dict) -> Response:
    """An htmx row action gets the table with the new state, so the page keeps its scroll position (#666); a normal
    POST (no JavaScript) gets the redirect to the trip page."""
    if request.headers.get("HX-Request"):
        return trip_page(request, trip_id, session, **view)
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


def _tokens_page(request: Request, session: Session, new_token: str | None = None, code: int = 200) -> HTMLResponse:
    tokens = session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())).all()
    server_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(request, "tokens.html", {"tokens": tokens, "new_token": new_token,
                                                               "server_url": server_url,
                                                               "userscripts": userscript_list(),
                                                               "bundle": bundle_info()}, status_code=code)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/pin",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_pin(request: Request, trip_id: int, itinerary_id: int, session: Session = Depends(get_session),
             view: dict = Depends(trip_view)) -> Response:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.pinned = not it.pinned
    session.commit()
    return _rows_or_redirect(request, trip_id, session, view)


@router.post("/trips/{trip_id}/return", dependencies=[Depends(require_login), Depends(verify_csrf)])
def make_return_trip(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """The return trip of a one-way trip (#340): the places swapped, one linked trip, no second one."""
    trip = _get_trip(session, trip_id)
    if trip.return_of_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a return trip cannot have a return trip")
    ret = session.scalar(select(Trip).where(Trip.return_of_id == trip.id))
    if ret is None:
        ret = Trip(title=f"{trip.title[:191]} (return)", origin_text=trip.destination_text,
                   destination_text=trip.origin_text, travelers=trip.travelers, profile_id=trip.profile_id,
                   return_of_id=trip.id)
        session.add(ret)
        session.commit()
    return RedirectResponse(f"/trips/{ret.id}/edit", status_code=303)


@router.post("/trips/{trip_id}/next", dependencies=[Depends(require_login), Depends(verify_csrf)])
def make_next_trip(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """The next part of a journey (#560): a new trip from the destination of the last trip of the chain."""
    journey = chain(_get_trip(session, trip_id))
    first, last = journey[0], journey[-1]
    new = Trip(title=f"{first.title[:180]} (part {len(journey) + 1})", origin_text=last.destination_text,
               destination_text=None, travelers=last.travelers, profile_id=last.profile_id, return_of_id=last.id)
    session.add(new)
    session.commit()
    return RedirectResponse(f"/trips/{new.id}/edit", status_code=303)


def _copy_of(trip: Trip, return_of_id: int | None = None) -> Trip:
    """A copy of a trip (#801): the places, travelers, profile, note and target price; no dates, offers or link
    (unless given)."""
    return Trip(title=f"{trip.title[:192]} (copy)", origin_text=trip.origin_text,
                destination_text=trip.destination_text, travelers=trip.travelers, profile_id=trip.profile_id,
                notes=trip.notes, target_price=trip.target_price, return_of_id=return_of_id)


@router.post("/trips/{trip_id}/copy", dependencies=[Depends(require_login), Depends(verify_csrf)])
def copy_trip(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """A copy of a trip for another date (#801)."""
    new = _copy_of(_get_trip(session, trip_id))
    session.add(new)
    session.commit()
    return RedirectResponse(f"/trips/{new.id}/edit", status_code=303)


@router.post("/trips/{trip_id}/copy-journey", dependencies=[Depends(require_login), Depends(verify_csrf)])
def copy_journey(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """A copy of a whole journey (#802): the same order, each copy linked to the copy before it."""
    previous, first_new = None, None
    for trip in chain(_get_trip(session, trip_id)):
        new = _copy_of(trip, return_of_id=previous.id if previous is not None else None)
        session.add(new)
        session.flush()  # the id links the next copy
        if first_new is None:
            first_new = new
        previous = new
    session.commit()
    return RedirectResponse(f"/trips/{first_new.id}/edit", status_code=303)


@router.post("/profiles",dependencies=[Depends(require_login), Depends(verify_csrf)])
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
                      first_class_hour: Decimal = Form(Weights.first_class_hour, ge=-1000, le=1000),
                      self_transfer_penalty: Decimal = Form(Weights.self_transfer_penalty, ge=0, le=1000),
                      stale_hours: int = Form(Weights.stale_hours, ge=1, le=720),
                      stale_penalty: Decimal = Form(Weights.stale_penalty, ge=0, le=1000),
                      hour_tier1_after_min: int = Form(Weights.hour_tier1_after_min, ge=0, le=2880),
                      hour_tier1_markup: Decimal = Form(Weights.hour_tier1_markup, ge=0, le=100),
                      hour_tier2_after_min: int = Form(Weights.hour_tier2_after_min, ge=0, le=2880),
                      hour_tier2_markup: Decimal = Form(Weights.hour_tier2_markup, ge=0, le=100),
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
                      first_class_hour=first_class_hour,
                      self_transfer_penalty=self_transfer_penalty, stale_hours=stale_hours,
                      stale_penalty=stale_penalty, hour_tier1_after_min=hour_tier1_after_min,
                      hour_tier1_markup=hour_tier1_markup, hour_tier2_after_min=hour_tier2_after_min,
                      hour_tier2_markup=hour_tier2_markup)
    save_profile(session, name.strip(), weights)
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


# The ranges of the weights in a form (#1013): the same as `weight_query()` and `save_profile_page()`.
# (low, high) for a number, None for a time of day.
WEIGHT_RANGES = {
    "hour_markup": (0, 100), "transfer_markup": (0, 100), "airport_before_min": (0, 1440),
    "airport_after_min": (0, 1440), "baggage_fee": (0, 1000), "early_limit": None, "late_limit": None,
    "time_window_penalty": (0, 1000), "night_start": None, "night_end": None, "night_min": (0, 1440),
    "night_adjust": (-1000, 1000), "night_hour_markup": (0, 100), "short_transfer_min": (0, 240),
    "short_transfer_penalty": (0, 1000), "train_markup": (-1000, 1000), "bus_markup": (-1000, 1000),
    "flight_markup": (-1000, 1000), "ferry_markup": (-1000, 1000), "flex_non_refundable": (-1000, 1000),
    "flex_partly_refundable": (-1000, 1000), "flex_flexible": (-1000, 1000), "first_class_hour": (-1000, 1000),
    "self_transfer_penalty": (0, 1000), "stale_hours": (1, 720), "stale_penalty": (0, 1000),
    "hour_tier1_after_min": (0, 2880), "hour_tier1_markup": (0, 100), "hour_tier2_after_min": (0, 2880),
    "hour_tier2_markup": (0, 100),
}


def form_weights(form) -> tuple[Weights, str | None]:
    """The `Weights` of a profile form (#1013) and the first error. A missing or empty field takes the `Weights`
    default (`night_hour_markup`: None, the same as the hour markup)."""
    values = {}
    for f in dataclasses.fields(Weights):
        raw = (form.get(f.name) or "").strip()
        if not raw:
            continue
        bounds = WEIGHT_RANGES[f.name]
        try:
            if bounds is None:
                values[f.name] = time.fromisoformat(raw)
                continue
            v = int(raw) if isinstance(f.default, int) else Decimal(raw)
        except (ValueError, InvalidOperation):
            return Weights(), f"{f.name}: {raw!r} is not a valid value; nothing changed."
        if isinstance(v, Decimal) and not v.is_finite():
            return Weights(), f"{f.name}: {raw!r} is not a valid value; nothing changed."
        if not bounds[0] <= v <= bounds[1]:
            return Weights(), f"{f.name}: {raw} is not in {bounds[0]} to {bounds[1]}; nothing changed."
        values[f.name] = v
    return Weights(**values), None


def _profile_form(request: Request, profile: ScoreProfile | None, name: str, weights: Weights,
                  error: str | None = None, code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, "profile_edit.html", {"profile": profile, "name": name,
                                      "weights": weights, "error": error}, status_code=code)


@router.get("/profiles/new", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def new_profile_page(request: Request) -> HTMLResponse:
    """A form with the `Weights` defaults for a new profile (#1013)."""
    return _profile_form(request, None, "", Weights())


@router.get("/profiles/{profile_id}", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def edit_profile_page(profile_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """A form with the stored weights of the profile (#1013)."""
    profile = session.get(ScoreProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    return _profile_form(request, profile, profile.name, from_config(profile.config_json))


@router.post("/profiles/new", response_class=HTMLResponse, dependencies=[Depends(require_login), Depends(verify_csrf)])
async def create_profile_page(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    name = (form.get("name") or "").strip()
    weights, error = form_weights(form)
    if error is None and not 1 <= len(name) <= 100:
        error = "A name needs 1 to 100 characters; nothing changed."
    if error is None and session.scalars(select(ScoreProfile.id).where(ScoreProfile.name == name)).first():
        error = f'The name "{name}" exists already; nothing changed.'
    if error is not None:
        return _profile_form(request, None, name, weights, error, 422)
    save_profile(session, name, weights)
    return RedirectResponse("/profiles", status_code=303)


@router.post("/profiles/{profile_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def update_profile_page(profile_id: int, request: Request, session: Session = Depends(get_session)):
    profile = session.get(ScoreProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    form = await request.form()
    name = (form.get("name") or "").strip()
    weights, error = form_weights(form)
    if error is None and not 1 <= len(name) <= 100:
        error = "A name needs 1 to 100 characters; nothing changed."
    if error is None and not update_profile(session, profile_id, name, weights):
        error = f'The name "{name}" exists already; nothing changed.'
    if error is not None:
        return _profile_form(request, profile, name, weights, error, 422)
    return RedirectResponse("/profiles", status_code=303)


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
def toggle_booked(request: Request, trip_id: int, itinerary_id: int, session: Session = Depends(get_session),
             view: dict = Depends(trip_view)) -> Response:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.booked = not it.booked
    session.commit()
    return _rows_or_redirect(request, trip_id, session, view)


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
    """The price history of each fare of an itinerary, the newest capture first (#240).

    The trip page loads it as a fragment (htmx sends HX-Request); a direct visit gets a page with its header."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    context = {"fares": it.fares, "chart": chart(it.fares)}
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "price_history.html", context)
    return templates.TemplateResponse(request, "price_history_page.html",
                                      {**context, "trip": session.get(Trip, trip_id)})


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/hide",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def toggle_hide(request: Request, trip_id: int, itinerary_id: int, session: Session = Depends(get_session),
             view: dict = Depends(trip_view)) -> Response:
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    it.hidden = not it.hidden
    session.commit()
    return _rows_or_redirect(request, trip_id, session, view)


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


RATE_CODE = re.compile(r"^[A-Z]{3}$")


def _rates_page(request: Request, session: Session, error: str | None = None, code: int = 200) -> HTMLResponse:
    rates = session.scalars(select(CurrencyRate).order_by(CurrencyRate.code)).all()
    return templates.TemplateResponse(request, "rates.html", {"rates": rates, "error": error}, status_code=code)


@router.get("/rates", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def rates_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _rates_page(request, session)


@router.post("/rates", response_model=None, dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_rate(request: Request, code: str = Form(""), rate: str = Form(""),
              session: Session = Depends(get_session)) -> HTMLResponse | RedirectResponse:
    """Add or change the EUR value of one unit of a currency (#384)."""
    code = code.strip().upper()
    try:
        value = Decimal(rate.strip())
    except InvalidOperation:
        value = None
    if not RATE_CODE.match(code) or code == "EUR":
        return _rates_page(request, session, "The code must be 3 letters and not EUR.", 422)
    if (value is None or not value.is_finite() or value <= 0 or value >= Decimal("100000000")
            or value.as_tuple().exponent < -6):
        return _rates_page(request, session, "The rate must be a number more than 0 with at most 6 decimals.", 422)
    row = session.get(CurrencyRate, code)
    now = datetime.now(timezone.utc)
    if row is None:
        session.add(CurrencyRate(code=code, eur_per_unit=value, updated_at=now))
    else:
        row.eur_per_unit, row.updated_at = value, now
    session.commit()
    return RedirectResponse("/rates", status_code=303)


@router.post("/rates/{code}/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_rate(code: str, session: Session = Depends(get_session)) -> RedirectResponse:
    row = session.get(CurrencyRate, code)
    if row is not None:
        session.delete(row)
        session.commit()
    return RedirectResponse("/rates", status_code=303)


BACKUP_MAX_AGE = timedelta(hours=48)


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def settings_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """General: the capture retention period and the state of the backups (#925)."""
    newest = newest_backup(Path(os.environ.get("BACKUP_DIR", "/backups")))
    return templates.TemplateResponse(request, "settings.html", {"backup": newest,
                                                                 "backup_old": newest is not None and
                                                                 datetime.now(timezone.utc) - newest[0] > BACKUP_MAX_AGE,
                                                                 "retention_days": retention_days(session),
                                                                 "max_days": MAX_RETENTION_DAYS})


@router.post("/settings", dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_settings(retention: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    """Saves only the field of the card "Captures": each card of a settings page saves its own fields (#925)."""
    value = retention.strip()
    if not value.isdigit() or int(value) > MAX_RETENTION_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"the retention period must be a whole number from 0 to {MAX_RETENTION_DAYS}")
    session.merge(Setting(key=RETENTION_KEY, value=str(int(value))))
    session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.get("/settings/messages", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def messages_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """The channel of the price-drop messages and Web Push on this device (#925)."""
    return templates.TemplateResponse(request, "settings_messages.html", {
        "channel": setting(session, CHANNEL_KEY, "none"), "channels": CHANNELS,
        "ntfy_url": setting(session, NTFY_URL_KEY), "notify_email": setting(session, EMAIL_KEY),
        "smtp_ready": bool(get_settings().smtp_host),
        "vapid_public_key": get_settings().vapid_public_key if webpush_ready() else "",
        "push_count": session.scalar(select(func.count()).select_from(PushSubscription)),
        "flash": request.session.pop("flash", None)})


@router.post("/settings/messages/test", dependencies=[Depends(require_login), Depends(verify_csrf)])
def test_message(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    """Send one test message by the active channel, with no wait for a price drop (#1086)."""
    click = str(request.base_url).rstrip("/") + "/settings/messages"
    msgs = alert_messages(session, "Test message from travel-aggregator",
                          "The channel of travel-aggregator works.", click)
    if msgs:
        deliver(msgs)
        request.session["flash"] = f"Test message sent by {msgs[0].channel}"
    else:
        request.session["flash"] = "Select a channel first"
    return RedirectResponse("/settings/messages", status_code=303)


@router.post("/settings/messages", dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_messages(notify_channel: str = Form("none"), ntfy_url: str = Form(""), notify_email: str = Form(""),
                  session: Session = Depends(get_session)) -> RedirectResponse:
    url = ntfy_url.strip()
    if notify_channel not in CHANNELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"the channel must be one of {', '.join(CHANNELS)}")
    if url and (not url.startswith("https://") or len(url) > 500):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the ntfy topic URL must start with https://")
    if notify_channel == "ntfy" and not url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the channel ntfy needs a topic URL")
    if notify_channel == "webpush" and not webpush_ready():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "the channel webpush needs VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_SUBJECT")
    address = notify_email.strip()
    if address and ("@" not in address or len(address) > 254):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the e-mail address needs an @")
    if notify_channel == "email" and not get_settings().smtp_host:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "E-mail needs SMTP_HOST on the server")
    if notify_channel == "email" and not address:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the channel email needs an address")
    session.merge(Setting(key=EMAIL_KEY, value=address))
    session.merge(Setting(key=CHANNEL_KEY, value=notify_channel))
    session.merge(Setting(key=NTFY_URL_KEY, value=url))
    session.commit()
    return RedirectResponse("/settings/messages", status_code=303)


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushIn(BaseModel):
    """The JSON of PushSubscription.toJSON() in the browser (#514); the server posts to the endpoint (P5: https only)."""
    endpoint: str = Field(pattern=r"^https://", max_length=1000)
    keys: PushKeys | None = None


@router.post("/settings/push", dependencies=[Depends(require_login), Depends(verify_csrf)])
def add_push(body: PushIn, session: Session = Depends(get_session)) -> dict:
    if body.keys is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the subscription needs the keys p256dh and auth")
    row = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is None:
        session.add(PushSubscription(endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth))
    else:
        row.p256dh, row.auth = body.keys.p256dh, body.keys.auth
    session.commit()
    return {"subscriptions": session.scalar(select(func.count()).select_from(PushSubscription))}


@router.post("/settings/push/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_push(body: PushIn, session: Session = Depends(get_session)) -> dict:
    row = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is not None:
        session.delete(row)
        session.commit()
    return {"subscriptions": session.scalar(select(func.count()).select_from(PushSubscription))}


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> Response:
    """The service worker of Web Push, at the root so that its scope is the whole app. No secret: no login."""
    return FileResponse(Path(__file__).parent / "static" / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


MANIFEST = {
    "name": "travel-aggregator",
    "short_name": "Travel",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#f5f5f7",
    "theme_color": "#5145d6",
    "icons": [
        {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}


@router.get("/manifest.webmanifest", include_in_schema=False)
def web_app_manifest() -> Response:
    """The web app manifest (#797): the name, colours and icons of the app on a phone. No secret: no login."""
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


COMPARE_ERROR = "Select 2 to 4 offers of this trip."


def _span(minutes: int) -> str:
    return f"{minutes // 60} h" if minutes % 60 == 0 else f"{minutes // 60} h {minutes % 60:02d} min"


def tradeoff_lines(rows, shown, source, places, weights: Weights, stale_before, rates,
                   trip_id: int, base_qs: dict, counts=None) -> dict:
    """The break-even line of each rendered row against the shown row with the lowest effective cost (#895).
    The best row and a row with no break-even get no line. Each line is (head, value, tail, link or None):
    the value is the link to this page with that hour value (#920)."""
    if not shown:
        return {}
    best = min(shown, key=lambda r: r[2].total)
    higher = dataclasses.replace(weights, hour_markup=weights.hour_markup + 1)
    def nxt(it):
        fares = [f for f in it.fares if not source or f.source == source]
        return row_cost(it, fares, places, higher, stale_before, rates, counts)[1].total
    best_next, lines, yours = nxt(best[0]), {}, _amount(weights.hour_markup)
    for it, _, cost in rows:
        if it.id == best[0].id:
            continue
        be = break_even(best[2].total, best_next, cost.total, nxt(it), weights.hour_markup)
        if be is None:
            continue
        dmin, dprice = best[0].duration_min - it.duration_min, cost.price - best[2].price
        time_part = (f"{_span(abs(dmin))} {'faster' if dmin > 0 else 'slower'}" if dmin else "same duration")
        price_part = (f"{_amount(abs(dprice))} {'more' if dprice > 0 else 'less'}" if dprice else "same price")
        # rounded up for "above", down for "below": the other row is the better one after the click (#896)
        rounding = ROUND_CEILING if be.better == "above" else ROUND_FLOOR
        rounded = be.hour_value.to_integral_value(rounding=rounding)
        link = None
        if Decimal(0) <= rounded <= 100:  # weight_query limits hour_markup to 0..100
            link = f"/trips/{trip_id}?" + urlencode({**base_qs, "hour_markup": str(int(rounded))}, doseq=True)
        lines[it.id] = (f"{time_part}, {price_part} than the best: better {be.better} ",
                        f"{_amount(be.hour_value)}/h", f" (yours: {yours}/h)", link)
    return lines


@router.get("/trips/{trip_id}/compare", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def compare_page(request: Request, trip_id: int, session: Session = Depends(get_session),
                 overrides: dict = Depends(weight_query), profile: int | None = Query(None),
                 it: list[int] = Query([])) -> HTMLResponse:
    """2 to 4 itineraries of a trip side by side, with the same effective cost as the trip table (#292)."""
    trip = _get_trip(session, trip_id)
    weights, chosen = resolve_weights(session, trip, overrides, profile)
    ids = list(dict.fromkeys(it))  # distinct, in the order of the URL
    found = {i.id: i for i in session.scalars(
        select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.id.in_(ids))
        .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()} if ids else {}
    query = {k: v for k, v in to_config(weights).items() if v is not None}
    if chosen is not None:
        query["profile"] = chosen.id
    context = {"trip": trip, "columns": [], "error": None, "sort_qs": urlencode(query, doseq=True),
               "format_breakdown": format_breakdown}
    if not 2 <= len(ids) <= 4 or any(i not in found or not found[i].fares for i in ids):
        context["error"] = COMPARE_ERROR
        return templates.TemplateResponse(request, "compare.html", context, status_code=400)
    places = session.scalars(select(AccessTime)).all()
    stale_before = datetime.now(timezone.utc) - timedelta(hours=weights.stale_hours)
    rates = load_rates(session)
    counts = fare_travelers(session, found.values())  # the same price per traveler as the trip page (#767)
    for i in ids:
        fare, cost = row_cost(found[i], found[i].fares, places, weights, stale_before, rates, counts)
        context["columns"].append((found[i], fare, cost))
    # the best column of each line: a tie marks every column with the lowest value (#294)
    lines = {"price": [c.price for _, _, c in context["columns"]],
             "duration": [it.duration_min for it, _, _ in context["columns"]],
             "transfers": [it.transfers for it, _, _ in context["columns"]],
             "cost": [c.total for _, _, c in context["columns"]]}
    context["best"] = {k: {n for n, v in enumerate(vals) if v == min(vals)} for k, vals in lines.items()}
    # the break-even hour value of each column against the lowest effective cost (#894)
    totals = [cost.total for _, _, cost in context["columns"]]
    higher = dataclasses.replace(weights, hour_markup=weights.hour_markup + 1)
    nexts = [row_cost(found[i], found[i].fares, places, higher, stale_before, rates, counts)[1].total for i in ids]
    best_n = totals.index(min(totals))  # a tie goes to the first column
    context["yours"] = _amount(weights.hour_markup)
    # a click on the value re-ranks the page with that hour value (#896): the other weights of the URL stay
    kept = [(k, v) for k, v in request.query_params.multi_items() if k != "hour_markup"]
    context["tradeoff"] = []  # (text, link or None) per column
    for n, (total, nxt) in enumerate(zip(totals, nexts)):
        if n == best_n:
            context["tradeoff"].append(("Best now", None))
            continue
        be = break_even(totals[best_n], nexts[best_n], total, nxt, weights.hour_markup)
        if be is None:
            context["tradeoff"].append(("—", None))
            continue
        # rounded up for "above", down for "below": the other offer is the better one after the click
        rounding = ROUND_CEILING if be.better == "above" else ROUND_FLOOR
        value = be.hour_value.to_integral_value(rounding=rounding)
        link = None
        if Decimal(0) <= value <= 100:
            link = f"/trips/{trip_id}/compare?" + urlencode(kept + [("hour_markup", str(int(value)))])
        context["tradeoff"].append((f"Better {be.better} {_amount(be.hour_value)}/h", link))
    return templates.TemplateResponse(request, "compare.html", context)
