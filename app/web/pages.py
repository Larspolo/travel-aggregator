"""The web pages: login, logout, the trips list, the trip page, the API tokens and the access and egress places and the settings. Jinja2 escapes all output: captured text is
untrusted (P5)."""

import dataclasses
import inspect
import json
import math
import os
import re
import time as clock
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, subqueryload

from app.storage import human_bytes, storage_use
from app.carriers import carrier_names as _carrier_names
from app.api.health import _built
from app.version import revisions
from app.web.userscripts import bundle_info, userscript_list
from app.auth import (EPOCH_KEY, NEW_TOTP_KEY, RECOVERY_SHOWN_KEY, TOTP_SECRET, TOTP_STEP, SESSION_EPOCH, SESSION_KEY, check_password, csrf_token, login_limiter,
                      require_login, safe_next, session_epoch, verify_csrf)
from app import departed, sales_open
from app.parsers import all_sources
from app.door import door_minutes
from app.compare_parts import part_rows
from app.pareto import pareto_ids
from app.pareto_chart import pareto_chart
from app.discount_cards import card_label, cards_warning, fare_cards
from app.delay_claim import claim as delay_claim
from app.backup import BACKUP_MAX_AGE, STAMP_FORMAT, newest_backup
import segno
from markupsafe import Markup

from app import login_log, passkeys, recovery, totp
from app.config import get_settings
from app.currency import by_eur, load_rates, to_eur
from app.fees import load_fees
from app.fallback import fallback_extras, no_fallback_marks
from app.trip_summary import trip_summary
from app.best_mode import best_per_mode
from app.trip_routes import _places as route_places, trip_routes
from app.days import day_sources, day_summary, return_grid, with_day_prices
from app.timeline import timeline
from app.filtered import hidden_counts
from app.split_suggest import split_skip, via_places
from app.db import get_session
from app.target import at_target
from app.drops import drops_by_trip, mark_seen, trip_drops
from app.door import baggage_extras, door_extras, flight_extras, trip_places
from app.flexibility import flexibility_extras
from app.travelclass import class_extras
from app.co2 import co2_extras, co2_kg
from app.tradeoff import best_at_price, best_range, break_even
from app.history import chart, trend_chart
from app.trend import trip_trend
from app.booked_overlap import conflicts
from app.duplicates import duplicate_trips
from app.book_timing import book_timing
from app.route_history import route_history
from app.money import money
from app.coverage import trip_coverage
from app.sales_open import horizons as sales_horizons
from app.sourcehealth import failing_sources
from app.carriers import carrier_names
from app.risk import carrier_extras, mode_extras, mode_hour_extras, reservation_extras, transfer_wait_extras, later_transfer_extras, work_hour_extras, self_transfer_extras, short_place_marks, stale_extras, station_change_extras, station_changes, transfer_extras, transfer_place_extras
from app.profiles import active_weights, default_weights, delete as delete_profile, from_config, list_profiles
from app.profiles import rename as rename_profile, save as save_profile, set_default as set_default_profile, to_config
from app.profiles import update_weights as update_profile
from app.same_journey import JoinError, join, split
from app.capture_changes import capture_changes
from app.models import (AccessTime, ApiToken, Capture, CurrencyRate, DayPrice, FarePrice, Itinerary, Passkey, PlaceName, PushSubscription, RailPass, ScoreProfile, Setting,
                        SentMessage, SourceFee, Trip, TripAccessTime)
from app.place_names import aliases as place_aliases
from app.tripmatch import ALIASES, fold
from app.notify import (CHANNEL_KEY, CHANNELS, EMAIL_KEY, MAX_REMINDER_DAYS, NTFY_URL_KEY, REMINDER_BEFORE_KEY,
                        REMINDER_DAYS_KEY, REMINDER_NOT_SENT, SOURCE_ALERT_KEY, alert_messages, deliver, setting,
                        webpush_ready)
from app.retention import MAX_RETENTION_DAYS, RETENTION_KEY, retention_days
from app.schemas import TripForm
from app.travel_day import MAX_TRAVEL_DAY_HOURS, TRAVEL_DAY_HOURS_KEY
from app.parsers import group_price
from app.rail_pass import pass_cost
from app.ranking import (Weights, _amount, bar_parts, effective_cost, for_group, format_breakdown, format_total, in_eur,
                         per_traveler)
from app.timeofday import arrive_by_extras, leave_after_extras, night_extras, night_time_extras, overnight_extras, time_extras
from app.timeofday import weekday_extras
from app.tokens import create as create_token, revoke as revoke_token
from app.trip_merge import is_linked, merge_choices
from app.trips import archived_journeys, chain, find_journeys, list_trips, past_trips, route_text, sort_journeys, tag_journeys

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["route_text"] = route_text
templates.env.globals["station_changes"] = station_changes
templates.env.globals["no_fallback_marks"] = no_fallback_marks
templates.env.globals["short_place_marks"] = short_place_marks
templates.env.globals["delay_claim"] = delay_claim  # the claim of a delayed booked row (#1692)
# All settings pages, in groups: the settings navigation of each settings page and the "Settings" link of the
# app bar use this one list (#925, DESIGN.md section 5, "Settings").
SETTINGS_NAV = [
    ("App", [("/settings", "General", "settings"), ("/settings/messages", "Messages", "chart")]),
    ("Ranking", [("/profiles", "Profiles", "user"), ("/places", "Places", "map-pin"),
                 ("/rates", "Exchange rates", "arrow-right-left"),
                 ("/fees", "Booking fees", "arrow-right-left"),
                 ("/passes", "Rail passes", "key")]),
    ("Capture", [("/tokens", "Userscripts", "key"), ("/sources/new", "Add a website", "plus")]),
]
SETTINGS_PATHS = [href for _, items in SETTINGS_NAV for href, _, _ in items]
templates.env.globals["settings_nav"] = SETTINGS_NAV
templates.env.globals["settings_paths"] = SETTINGS_PATHS


def _has_carrier(raw, name):
    """True when the name is one of the names of `carrier_names(raw)` or a part of the raw text, without case (#2249)."""
    names = {n.casefold() for n in carrier_names(raw)} | {p.strip().casefold() for p in (raw or "").split(", ")}
    return name.strip().casefold() in names - {""}


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


def day_cover(trip, itineraries, days, stale_before, today: date | None = None, horizon: dict | None = None) -> dict[str, tuple]:
    """For each day of `days`: the names of the sources with offers that day, the (name, link) of that day for each
    other source with a link (#2058), the (name, link or None) of each stale source of that day (#2114), and the
    (name, date its sales open) of each source whose sales of that day open today or later (#2254: no search link).
    A source with offers that day is left out. A trip with no date gives no entry."""
    if not trip.date_from:
        return {}
    from app.days import day_stale_sources
    from app.search_links import day_links
    found = day_sources(itineraries, lambda it: depart_day(it) if it.legs else None)
    stale = day_stale_sources(itineraries, lambda it: depart_day(it) if it.legs else None, stale_before)
    cover = {}
    for d in days:
        key = str(d.day)
        links = day_links(trip, date.fromisoformat(key))
        sources = found.get(key, [])
        names = [links[s][0] if s in links else s for s in sources]
        opens = {s: date.fromisoformat(key) - timedelta(days=n) for s, n in (horizon or {}).items()}
        closed = {s: day for s, day in opens.items()
                  if today is not None and day >= today and s not in sources}
        missing = [(name, url) for source, (name, url) in links.items()
                   if source not in sources and url and source not in closed]
        stale_links = [(links[s][0], links[s][1]) if s in links else (s, None) for s in stale.get(key, [])]
        cover[key] = (names, missing, stale_links,
                      [(links[s][0] if s in links else s, day) for s, day in closed.items()])
    return cover


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


def web_url(url: str | None) -> str | None:
    """The address if it is a web page (`http://` or `https://`), else None: the one rule for "Open search" links (#2079)."""
    if url and url.lower().startswith(("http://", "https://")):
        return url
    return None


templates.env.filters["web_url"] = web_url
templates.env.filters["money"] = money
templates.env.filters["mode_icon"] = mode_icon


def carrier_label(raw: str | None) -> str:
    """The carrier names of a raw carrier text (one name per carrier, #2250), joined with ", "; "?" if none."""
    return ", ".join(_carrier_names(raw)) or "?"


templates.env.filters["carrier_names"] = carrier_label
templates.env.filters["day_gap"] = day_gap
templates.env.filters["ago"] = ago
templates.env.filters["by_eur"] = by_eur
templates.env.filters["human_bytes"] = human_bytes
templates.env.filters["browser"] = login_log.browser_name


def _login_page(request: Request, session: Session, error: str | None = None, status_code: int = 200) -> HTMLResponse:
    has_passkey = session.scalar(select(func.count()).select_from(Passkey)) > 0
    return templates.TemplateResponse(request, "login.html", {"error": error, "passkeys": has_passkey},
                                      status_code=status_code)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    target = safe_next(request.query_params.get("next"))
    if target != "/":
        request.session[LOGIN_NEXT] = target
    else:
        request.session.pop(LOGIN_NEXT, None)
    return _login_page(request, session)


LOGIN_NEXT = "login_next"  # the session key: the page to open after the login (#2103)


TOTP_PENDING = "totp_pending"  # the login session key: the time of a correct password before the code (#1315)
TOTP_PENDING_MAX = 300


def _log_in(request: Request, session: Session) -> str:
    """Log in and give the page to go to."""
    target = safe_next(request.session.get(LOGIN_NEXT))
    request.session.clear()
    request.session[SESSION_KEY] = True
    request.session[EPOCH_KEY] = session_epoch(session)
    csrf_token(request)  # a new token after the login
    return target


def _pending(request: Request) -> bool:
    started = request.session.get(TOTP_PENDING)
    return isinstance(started, (int, float)) and 0 <= clock.time() - started <= TOTP_PENDING_MAX


@router.get("/login/code", response_class=HTMLResponse)
def login_code_form(request: Request) -> Response:
    if not _pending(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "login_code.html", {})


@router.post("/login/code", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def login_code(request: Request, code: str = Form(""), session: Session = Depends(get_session)) -> Response:
    address = request.client.host if request.client else "unknown"
    wait = login_limiter.retry_after(address)
    if wait:
        minutes = math.ceil(wait / 60)
        return HTMLResponse(f"Too many attempts. Try again in {minutes} minutes.", status_code=429,
                            headers={"Retry-After": str(wait)})
    secret = session.get(Setting, TOTP_SECRET)
    if not _pending(request) or secret is None:
        request.session.pop(TOTP_PENDING, None)
        return RedirectResponse("/login", status_code=303)
    last = session.get(Setting, TOTP_STEP)
    step = totp.check(secret.value, code, clock.time(), int(last.value) if last else -1)
    if step is None and recovery.use(session, code):  # a recovery code of the lost phone (#1316)
        login_log.record(session, request, "recovery")
        session.commit()
    elif step is None:
        login_limiter.failure(address)
        login_log.record(session, request, "code-failed")
        session.commit()
        return templates.TemplateResponse(request, "login_code.html", {"error": "Wrong code."}, status_code=401)
    else:
        session.merge(Setting(key=TOTP_STEP, value=str(step)))
        login_log.record(session, request, "code")
        session.commit()
    login_limiter.success(address)
    return RedirectResponse(_log_in(request, session), status_code=303)


@router.post("/login", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def login(request: Request, password: str = Form(""), session: Session = Depends(get_session)) -> HTMLResponse:
    address = request.client.host if request.client else "unknown"
    wait = login_limiter.retry_after(address)
    if wait:
        minutes = math.ceil(wait / 60)
        return HTMLResponse(f"Too many attempts. Try again in {minutes} minutes.", status_code=429,
                            headers={"Retry-After": str(wait)})
    if check_password(password, get_settings().owner_password_hash):
        target = request.session.get(LOGIN_NEXT)
        request.session.clear()
        if target:
            request.session[LOGIN_NEXT] = target
        if session.get(Setting, TOTP_SECRET) is not None:
            # The second step (#1315): the password alone does not log in.
            request.session[TOTP_PENDING] = clock.time()
            csrf_token(request)
            return RedirectResponse("/login/code", status_code=303)
        login_limiter.success(address)
        login_log.record(session, request, "ok")
        session.commit()
        return RedirectResponse(_log_in(request, session), status_code=303)
    login_limiter.failure(address)
    login_log.record(session, request, "failed")
    session.commit()
    return _login_page(request, session, "Wrong password.", 401)


def _too_many(address: str) -> JSONResponse | None:
    wait = login_limiter.retry_after(address)
    if not wait:
        return None
    return JSONResponse({"error": f"Too many attempts. Try again in {math.ceil(wait / 60)} minutes."}, status_code=429,
                        headers={"Retry-After": str(wait)})


@router.post("/login/passkey/options", dependencies=[Depends(verify_csrf)])
def login_passkey_options(request: Request) -> Response:
    """The options of navigator.credentials.get() for "Log in with a passkey" (#1559)."""
    address = request.client.host if request.client else "unknown"
    return _too_many(address) or Response(passkeys.authentication_options(request), media_type="application/json")


@router.post("/login/passkey", dependencies=[Depends(verify_csrf)])
def login_passkey(request: Request, credential: dict = Body(...), session: Session = Depends(get_session)) -> JSONResponse:
    """A good stored passkey logs in with no password and no one-time code; a bad one counts as a failed login (#1559)."""
    address = request.client.host if request.client else "unknown"
    if (busy := _too_many(address)) is not None:
        return busy
    try:
        passkeys.authenticate(request, session, credential)
    except passkeys.PasskeyError as e:
        session.rollback()
        login_limiter.failure(address)
        login_log.record(session, request, "passkey-failed")
        session.commit()
        return JSONResponse({"error": str(e)}, status_code=401)
    login_log.record(session, request, "passkey")
    session.commit()
    login_limiter.success(address)
    return JSONResponse({"next": _log_in(request, session)})


@router.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def new_by_trip(session: Session) -> dict[int, int]:
    """The count of itineraries since the last full view of each viewed trip, in one query (#1091)."""
    q = (select(Itinerary.trip_id, func.count()).join(Trip, Trip.id == Itinerary.trip_id)
         .where(Trip.viewed_at.is_not(None), Itinerary.first_seen_at > Trip.viewed_at).group_by(Itinerary.trip_id))
    return {trip_id: n for trip_id, n in session.execute(q)}


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def index(request: Request, archived: bool = False, q: str = Query("", max_length=200),
          tag: str = Query("", max_length=20), sort: str = Query("date", max_length=20),
          session: Session = Depends(get_session)) -> HTMLResponse:
    rows = list_trips(session)
    sort = sort if sort in ("date", "price", "capture", "title") else "date"
    # the newest capture of each trip, only for the sort by capture (#1973)
    captured = dict(session.execute(select(Capture.trip_id, func.max(Capture.captured_at))
                                    .group_by(Capture.trip_id)).all()) if sort == "capture" else {}
    archived_count = sum(1 for kind, _, _ in archived_journeys(rows, True) if kind == "trip")
    # a search on the trips list also finds the archived trips, below the other results (#1222)
    archived_lines = sort_journeys(tag_journeys(find_journeys(rows, q, True), tag), sort, captured) \
        if q.strip() and not archived else []
    archived_found = sum(1 for kind, _, _ in archived_lines if kind == "trip")
    return templates.TemplateResponse(request, "trips.html",
                                      {"lines": sort_journeys(tag_journeys(find_journeys(rows, q, archived), tag), sort, captured),
                                       "q": q.strip(), "tag": tag.strip(), "sort": sort, "drops": drops_by_trip(session),
                                       "new": new_by_trip(session), "archived": archived, "archived_count": archived_count,
                                       "archived_lines": archived_lines, "archived_found": archived_found,
                                       "failing": failing_sources(session),
                                       "past_count": 0 if archived else len(past_trips(rows, date.today()))})


@router.post("/trips/archive-past", dependencies=[Depends(require_login), Depends(verify_csrf)])
def archive_past(session: Session = Depends(get_session)) -> RedirectResponse:
    """Archive the trips whose journey is in the past (#1998). The server computes the ids again: it trusts no form ids."""
    for trip_id in past_trips(list_trips(session), date.today()):
        trip = session.get(Trip, trip_id)
        if trip is not None:
            trip.status = "archived"
    session.commit()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


FORM_FIELDS = tuple(TripForm.model_fields)


def _form_page(request: Request, values: dict, errors: list[str], trip_id: int | None, session: Session,
               code: int = 200, split_error: str | None = None):
    journey = len(chain(_get_trip(session, trip_id))) if trip_id else 1  # the button "Copy journey" (#802)
    splittable = trip_id is not None and _get_trip(session, trip_id).split_of_id is None  # "Split via" (#1177)
    merge = None  # "Merge into another trip" (#1262)
    if trip_id is not None:
        trip = _get_trip(session, trip_id)
        merge = {"linked": is_linked(session, trip), "choices": merge_choices(session, trip)}
    via = _split_places(session, _get_trip(session, trip_id)) if splittable else []
    return templates.TemplateResponse(request, "trip_form.html",
                                      {"values": values, "errors": errors, "trip_id": trip_id, "journey": journey,
                                       "splittable": splittable, "split_error": split_error, "merge": merge,
                                       "via_places": via, "place_kinds": PLACE_KINDS,
                                       "trip_places": _trip_places(session, trip_id) if trip_id else [],
                                       "profiles": list_profiles(session),
                                       "rail_passes": session.scalars(
                                           select(RailPass).order_by(RailPass.first_day, RailPass.name)).all()},
                                      status_code=code)


def _split_places(session: Session, trip: Trip) -> list[tuple[str, int]]:
    """The transfer places of the shown offers of a trip, for the buttons "Split via" (#1459)."""
    itineraries = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False))
                                  .options(subqueryload(Itinerary.legs))).all()
    return via_places(itineraries, split_skip(trip))


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
    if data.rail_pass_id is not None and session.get(RailPass, data.rail_pass_id) is None:
        return _form_page(request, values, [f"rail_pass_id: no pass {data.rail_pass_id}"], trip.id if trip else None,
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
                 overnight_min: int | None = Query(None, ge=0, le=1440),
                 overnight_cost: Decimal | None = Query(None, ge=0, le=1000),
                 wait_hour_markup: Decimal | None = Query(None, ge=0, le=100),
                 leave_hour_markup: Decimal | None = Query(None, ge=0, le=200),  # (#2022)
                 night_hour_markup: Decimal | None = Query(None, ge=0, le=100),
                 short_transfer_min: int | None = Query(None, ge=0, le=240),
                 short_transfer_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 station_change_min: int | None = Query(None, ge=0, le=240),
                 station_change_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 no_fallback_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 flex_non_refundable: Decimal | None = Query(None, ge=-1000, le=1000),
                 flex_partly_refundable: Decimal | None = Query(None, ge=-1000, le=1000),
                 flex_flexible: Decimal | None = Query(None, ge=-1000, le=1000),
                 first_class_hour: Decimal | None = Query(None, ge=-1000, le=1000),
                 self_transfer_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 reservation_fee: Decimal | None = Query(None, ge=0, le=1000),
                 currency_fee_pct: Decimal | None = Query(None, ge=0, le=10),
                 stale_hours: int | None = Query(None, ge=1, le=720),
                 stale_penalty: Decimal | None = Query(None, ge=0, le=1000),
                 train_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 bus_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 flight_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 co2_price_kg: Decimal | None = Query(None, ge=0, le=10),
                 co2_train_kg_h: Decimal | None = Query(None, ge=0, le=1000),
                 co2_bus_kg_h: Decimal | None = Query(None, ge=0, le=1000),
                 co2_flight_kg_h: Decimal | None = Query(None, ge=0, le=1000),
                 co2_ferry_kg_h: Decimal | None = Query(None, ge=0, le=1000),
                 ferry_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 hour_tier1_after_min: int | None = Query(None, ge=0, le=2880),
                 hour_tier1_markup: Decimal | None = Query(None, ge=0, le=100),
                 hour_tier2_after_min: int | None = Query(None, ge=0, le=2880),
                 hour_tier2_markup: Decimal | None = Query(None, ge=0, le=100),
                 carrier1_name: str | None = Query(None, max_length=50),
                 carrier1_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 carrier2_name: str | None = Query(None, max_length=50),
                 carrier2_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 carrier3_name: str | None = Query(None, max_length=50),
                 carrier3_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 weekday1_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 weekday2_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 weekday3_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 weekday4_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 weekday5_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 weekday6_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 weekday7_markup: Decimal | None = Query(None, ge=-1000, le=1000),  # (#2136)
                 transfer_place1_name: str | None = Query(None, max_length=100),  # (#1851)
                 transfer_place1_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 transfer_place2_name: str | None = Query(None, max_length=100),
                 transfer_place2_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 transfer_place3_name: str | None = Query(None, max_length=100),
                 transfer_place3_markup: Decimal | None = Query(None, ge=-1000, le=1000),
                 transfer_place1_min: str | None = Query(None, max_length=20),  # (#2073)
                 transfer_place2_min: str | None = Query(None, max_length=20),  # (#2073)
                 transfer_place3_min: str | None = Query(None, max_length=20),  # (#2073)
                 train_hour_markup: str | None = Query(None, max_length=20),  # (#1568)
                 bus_hour_markup: str | None = Query(None, max_length=20),  # (#1568)
                 flight_hour_markup: str | None = Query(None, max_length=20),  # (#1568)
                 ferry_hour_markup: str | None = Query(None, max_length=20),  # (#1568)
                 transfer_wait_hour_markup: str | None = Query(None, max_length=20),  # (#2221)
                 later_transfer_markup: str | None = Query(None, max_length=20),  # (#2302)
                 night_seat_adjust: str | None = Query(None, max_length=20),  # (#1808)
                 night_couchette_adjust: str | None = Query(None, max_length=20),  # (#1808)
                 night_sleeper_adjust: str | None = Query(None, max_length=20)) -> dict:  # (#1808)
    """The weights of the URL; None = not in the URL, the profile gives the value (#230). An hour value per mode
    (#1568) that is sent blank is `MODE_HOUR_BLANK`: the hour markup, also when the profile has a value."""
    values = dict(locals())
    for name in MODE_HOUR_FIELDS:
        values[name] = _mode_hour(name, values[name])
    return values


# The optional weights whose blank field in the URL means None (#1568, #1808), with their range.
OPTIONAL_RANGES = {"train_hour_markup": (0, 100), "bus_hour_markup": (0, 100), "flight_hour_markup": (0, 100),
                   "ferry_hour_markup": (0, 100), "transfer_wait_hour_markup": (0, 100),  # (#2221)
                   "later_transfer_markup": (0, 100),  # (#2302)
                   "night_seat_adjust": (-1000, 1000),
                   "night_couchette_adjust": (-1000, 1000), "night_sleeper_adjust": (-1000, 1000),
                   "transfer_place1_min": (0, 240), "transfer_place2_min": (0, 240), "transfer_place3_min": (0, 240)}
MODE_HOUR_FIELDS = tuple(OPTIONAL_RANGES)
MODE_HOUR_BLANK = ""  # a blank field of the live re-ranking (#1568): None in the weights, not the profile value


def _mode_hour(name: str, raw: str | None) -> Decimal | str | None:
    """An optional value in the URL (#1568, #1808): None (not sent), MODE_HOUR_BLANK, or a Decimal in its range."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return MODE_HOUR_BLANK
    try:
        value = Decimal(raw)
    except InvalidOperation:
        value = None
    low, high = OPTIONAL_RANGES[name]
    if value is None or not value.is_finite() or not low <= value <= high:
        raise HTTPException(422, f"{name}: {raw!r} is not in {low} to {high}")
    if name.endswith("_min"):  # a number of minutes (#2073)
        if value != value.to_integral_value():
            raise HTTPException(422, f"{name}: {raw!r} is not a whole number")
        return int(value)
    return value


def resolve_weights(session: Session, trip: Trip, overrides: dict, profile: int | None):
    """The active weights and the chosen profile (#232): a weight in the URL, the profile of the URL (#231), the
    profile of the trip, the default one. An unknown id in the URL gives the default profile, no error."""
    if profile is not None:
        chosen = session.get(ScoreProfile, profile)
    else:
        chosen = session.get(ScoreProfile, trip.profile_id) if trip.profile_id is not None else None
    base = from_config(chosen.config_json) if chosen is not None else default_weights(session)
    blank = {k: None for k, v in overrides.items() if v == MODE_HOUR_BLANK and k in MODE_HOUR_FIELDS}  # (#1568)
    weights = active_weights(base, {k: v for k, v in overrides.items() if k not in blank})
    return dataclasses.replace(weights, **blank), chosen  # the score is computed here and never stored


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


def _source_name(source: str) -> str:
    """The name of a source in the search links (#1142), else the source itself."""
    from app.search_links import load_sources
    names = {v.get("source"): v.get("name") for v in load_sources().values() if isinstance(v, dict)}
    return names.get(source) or source


def fee_extras(fare, fees: dict, travelers: int) -> tuple[tuple[str, Decimal], ...]:
    """The part "<name> fee" of the booking fee of the source of the fare (#1143), per traveler: the fee of the
    trip is split over its travelers. A fee of 0 or no fee for the source adds no part."""
    amount = fees.get(fare.source, Decimal(0)) / max(travelers, 1)
    if amount == 0:
        return ()
    return ((f"{_source_name(fare.source)} fee", amount),)


def currency_fee_extras(fare, eur: Decimal | None, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """The part "currency fee" (#1993): `currency_fee_pct` percent of the EUR price per traveler of a fare that is not
    in EUR. A fare with no rate (`eur` None), a EUR fare and a percent of 0 add no part."""
    if fare.currency == "EUR" or eur is None or weights.currency_fee_pct <= 0:
        return ()
    return (("currency fee", eur * weights.currency_fee_pct / 100),)


def row_cost(it: Itinerary, fares, places, weights: Weights, stale_before: datetime, rates=None, counts=None,
             fees=None):
    """The main fare of one itinerary and its effective cost: the lowest cost, a tie goes to the lowest price (#175).
    The cost uses the EUR value of the price (`rates` of `load_rates()`, #385); a fare with no rate comes last.
    The price part is per traveler (`counts` of `fare_travelers()`, #767); the other parts are per person.
    The booking fee of the source of a fare is a part of its cost (`fees` of `load_fees()`, #1143)."""
    rates, counts, fees = rates or {}, counts or {}, fees or {}
    travelers = it.trip.travelers if fees else 1  # the trip is read only when a fee can add a part
    base = (door_extras(it, places, weights.hour_markup) + flight_extras(it, weights) + time_extras(it, weights)
                + weekday_extras(it, weights)
            + overnight_extras(it, weights) + night_time_extras(it, weights) + mode_extras(it, weights)
                + mode_hour_extras(it, weights) + transfer_wait_extras(it, weights) + later_transfer_extras(it, weights)
                + work_hour_extras(it, weights)
            + carrier_extras(it, weights) + transfer_place_extras(it, weights) + co2_extras(it, weights)
            + (arrive_by_extras(it, it.trip.arrive_by, weights) if weights.wait_hour_markup else ())
            + (leave_after_extras(it, it.trip.leave_after, weights) if weights.leave_hour_markup else ())
            + transfer_extras(it, weights) + station_change_extras(it, weights) + fallback_extras(it, weights)
                + stale_extras(it, weights, stale_before))
    rail_pass = getattr(it.trip, "rail_pass", None)  # #2267: the pass cost replaces the fare price
    covered = pass_cost(it, rail_pass) if rail_pass is not None else None
    def cost(f):
        if covered is not None:  # the owner does not pay the fare: no price, currency or group text
            return effective_cost(Decimal(0), it.duration_min, it.transfers, weights,
                                  ((f"pass {rail_pass.name}", covered),) + base + night_extras(it, weights, f)
                                  + flexibility_extras(f, weights) + baggage_extras(f, it, weights, rates)
                                  + class_extras(f, it.duration_min, weights) + self_transfer_extras(f, weights)
                                  + reservation_extras(f, weights) + fee_extras(f, fees, travelers))
        eur, n = to_eur(f.latest_price, f.currency, rates), counts.get(f.id)
        per = per_traveler(eur, n) if eur is not None else None
        b = effective_cost(per if per is not None else Decimal(0), it.duration_min, it.transfers, weights,
                           base + night_extras(it, weights, f) + flexibility_extras(f, weights) + baggage_extras(f, it, weights, rates) + class_extras(f, it.duration_min, weights)
                               + self_transfer_extras(f, weights) + reservation_extras(f, weights)
                               + fee_extras(f, fees, travelers) + currency_fee_extras(f, per, weights))
        return for_group(in_eur(b, f.latest_price, f.currency, eur), f.latest_price, f.currency, n)
    tie = (lambda b: covered) if covered is not None else (lambda b: b.price)  # the lowest price, or the pass cost
    return min(((f, cost(f)) for f in fares), key=lambda fc: (fc[1].total, tie(fc[1])))


def current_fares(fares, gone):
    """The fares that are not gone (#1386), or all fares when all are gone: a gone fare does not rank."""
    now = [f for f in fares if f.id not in gone]
    return now or list(fares)


def current_rows(rows, gone):
    """The (itinerary, fare, cost) rows whose main fare is not gone, or all rows when none is current (#1386)."""
    return [r for r in rows if r[1].id not in gone] or rows


def _gone(session: Session, its) -> dict:
    """The fares that do not rank: the gone fares (#1386) and the suspect fares (#1605)."""
    gone, suspect = _gone_and_suspect(session, its)
    return {**suspect, **gone}


def _gone_and_suspect(session: Session, its) -> tuple[dict, dict]:
    from app.gone import gone_fares
    from app.suspect import suspect_fares
    trip_ids = {it.trip_id for it in its}
    return gone_fares(session, trip_ids), suspect_fares(session, trip_ids)


def _chosen_offer(session: Session, trip: Trip, weights: Weights, places, now: datetime):
    """The chosen offer of one direction (#342): booked, else pinned, else any; the lowest effective cost in the group.
    Hidden and departed offers never count (#1391). None when the direction has no visible offer with a fare."""
    stale_before = now - timedelta(hours=weights.stale_hours)
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False),
                                                  departed.not_departed(now))
                          .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = trip_places(session, trip)  # the places of this trip, not of the journey (#2109)
    rates = load_rates(session)
    counts, fees, gone = fare_travelers(session, its), load_fees(session), _gone(session, its)
    rows = [(it, *row_cost(it, current_fares(it.fares, gone), places, weights, stale_before, rates, counts, fees))
            for it in its if it.fares]
    rows = current_rows(rows, gone)
    if not rows:
        return None
    return min(rows, key=lambda r: (not r[0].booked, not r[0].pinned, r[2].total, r[0].depart_at))


def best_offer(session: Session, trip: Trip):
    """The best offer of the trip for the ingest response (#880): the lowest effective cost of the visible itineraries
    with fares, by the profile of the trip (else the default); a tie goes to the lowest departure.
    Returns (itinerary, fare, cost) or None."""
    weights, _ = resolve_weights(session, trip, {}, None)
    return best_for_weights(session, trip, weights)


def best_for_weights(session: Session, trip: Trip, weights: Weights, now: datetime | None = None):
    """The first row of the ranked table with `weights` and no page filters (#1210): the lowest effective cost of the
    visible, not departed (#1391) itineraries with fares; a tie goes to the lowest departure. Returns (itinerary, fare, cost) or None."""
    now = now or datetime.now(timezone.utc)
    stale_before = now - timedelta(hours=weights.stale_hours)
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.hidden.is_(False),
                                                  departed.not_departed(now))
                          .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = trip_places(session, trip)  # (#2109)
    rates = load_rates(session)
    counts, fees, gone = fare_travelers(session, its), load_fees(session), _gone(session, its)
    rows = [(it, *row_cost(it, current_fares(it.fares, gone), places, weights, stale_before, rates, counts, fees))
            for it in its if it.fares]
    rows = current_rows(rows, gone)
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


def round_trip_grid(session: Session, trip: Trip, days, places, now: datetime):
    """The grid of a round trip (#1108): rows are the outbound days, columns the return days. None when the chain of
    the trip does not have exactly 2 trips. The present trip uses its days of the page; the other trip its own profile.
    Returns (grid, the index of the present trip: 0 outbound, 1 return)."""
    parts = chain(trip)
    if len(parts) != 2:
        return None
    other = parts[1] if parts[0].id == trip.id else parts[0]
    w = resolve_weights(session, other, {}, None)[0]
    stale_before = now - timedelta(hours=w.stale_hours)
    its = session.scalars(select(Itinerary).where(Itinerary.trip_id == other.id, Itinerary.hidden.is_(False),
                                                  departed.not_departed(now))
                          .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    rates, counts, fees = load_rates(session), fare_travelers(session, its), load_fees(session)
    gone = _gone(session, its)
    rows = [(it, *row_cost(it, current_fares(it.fares, gone), places, w, stale_before, rates, counts, fees))
            for it in its if it.fares]
    rows = current_rows(rows, gone)
    other_days = day_summary(rows, other.date_from, other.date_to, lambda it: depart_day(it) if it.legs else None)
    present = 0 if parts[0].id == trip.id else 1
    outbound, back = (days, other_days) if present == 0 else (other_days, days)
    return {"grid": return_grid(outbound, back), "present": present}


def split_sections(session: Session, trip: Trip, weights: Weights, places, now: datetime, best_direct):
    """The sections "Split tickets via X" (#1179): one per pair of split trips (in id order), ranked with the weights
    of the page, so the live re-rank updates them. Each: the place, the two parts, the best pairs and the difference
    of each pair to the best direct offer (`best_direct`, a Decimal or None)."""
    from app.search_links import links_for_trip
    from app.split import split_pairs
    parts = list(trip.split_trips)
    if not parts:
        return []
    stale_before = now - timedelta(hours=weights.stale_hours)
    rates, fees = load_rates(session), load_fees(session)

    def ranked(t: Trip):
        its = session.scalars(select(Itinerary).where(Itinerary.trip_id == t.id, Itinerary.hidden.is_(False),
                                                      departed.not_departed(now))
                              .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
        counts = fare_travelers(session, its)
        return [(it, *row_cost(it, it.fares, places, weights, stale_before, rates, counts, fees))
                for it in its if it.fares and it.legs]
    sections = []
    for a, b in zip(parts[0::2], parts[1::2]):
        first, second = ranked(a), ranked(b)
        pairs = []
        for p in split_pairs(first, second, weights):
            diff = p.total - best_direct if best_direct is not None and best_direct.is_finite() else None
            wait = int((p.second[0].depart_at - p.first[0].arrive_at).total_seconds() // 60)
            pairs.append({"pair": p, "diff": diff, "wait": wait})
        sections.append({"via": a.destination_text or b.origin_text or "?", "parts": [
            {"trip": t, "count": len(r), "links": [] if r else links_for_trip(t)} for t, r in ((a, first), (b, second))],
            "pairs": pairs})
    return sections


def route_value(key: tuple) -> str:
    """The `route` query value of a route key (#2225): the places joined by " > "; "Direct" for no place.

    The keys are casefolded, so "Direct" never is the value of a place "direct".
    """
    return " > ".join(key) if key else "Direct"


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
              latest_arrive: str | None = Query(None, pattern=CLOCK_PATTERN),
              day: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
              exclude_mode: list[Annotated[str, Field(max_length=50)]] = Query([]),
              exclude_carrier: list[Annotated[str, Field(max_length=50)]] = Query([]),
              show_hidden: bool = Query(False),
              show_departed: bool = Query(False),
              hide_stale: bool = Query(False),
              pareto_only: bool = Query(False, alias="pareto"),  # "only these": the marked offers (#1857)
              route: str = Query("", max_length=200),  # route_value() of a route; "" = all (#2225)
              capture: int | None = Query(None),  # with `change`: only the changes of this capture (#2329)
              change: str = Query("", max_length=10),
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
    # without a latest_arrive in the query, the arrive-by time of the trip is the limit (#1296); an empty one is no limit
    if latest_arrive is None:
        latest_arrive = trip.arrive_by.strftime("%H:%M") if trip.arrive_by else ""
    limit_arrive = time.fromisoformat(latest_arrive) if latest_arrive else None
    # subqueryload: one statement per relation; selectinload adds one per 500 offers (#115)
    hidden_filter = [] if show_hidden else [Itinerary.hidden.is_(False)]  # "show hidden" (#200)
    departed_now = departed.clock()
    if not show_departed:
        hidden_filter.append(departed.not_departed(departed_now))  # "show departed" (#1391)
    itineraries = session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, *hidden_filter)
                                  .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    places = trip_places(session, trip)  # once per request; the overrides of the trip (#2109)
    rates = load_rates(session)  # once per request (#385)
    counts = fare_travelers(session, itineraries)  # once per request (#767)
    fees = load_fees(session)  # once per request (#1143)
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(hours=weights.stale_hours)  # a row older than this is stale (#275)
    # the fares of an older search (#1386) and the fares with an implausible price (#1605) do not rank
    gone_marks, suspect = _gone_and_suspect(session, itineraries) if itineraries else ({}, {})
    gone = {**suspect, **gone_marks}
    rows, all_rows, modes, sources, carriers, tests = [], [], set(), set(), set(), []
    hides_of = {}  # the labels of the filters that hide each row: the same sets as `tests` (#1857)
    best_hidden = None  # (fare, cost, itinerary, labels) of the lowest cost that a filter hides (#1454)
    for it in itineraries:
        if not it.fares:
            continue  # an itinerary with no fare has no cost: it is not a row
        it_modes = {m for m in (it.mode_summary or "").split("+") if m}
        modes |= it_modes
        sources |= {f.source for f in it.fares}
        carriers |= {c for leg in it.legs for c in carrier_names(leg.carrier)}
        fares = current_fares([f for f in it.fares if not source or f.source == source], gone)
        # each filter test once per row (#1452): the same tests hide the row and count it
        hides = {label for label, hit in (
            (f"mode {mode}", mode and mode not in it_modes),  # #112
            (f"source {source}", not fares),
            (f"max transfers {limit_transfers}", limit_transfers is not None and it.transfers > limit_transfers),
            (f"max duration {limit_duration} min", limit_duration is not None and it.duration_min > limit_duration),
            (f"depart after {earliest_depart}",  # the time limits (#181)
             limit_depart is not None and it.legs and not in_time_window(it, limit_depart, None)),
            (f"arrive by {latest_arrive}",
             limit_arrive is not None and it.legs and not in_time_window(it, None, limit_arrive)),
            # "hide stale" hides a row whose newest capture is stale (#277)
            ("hide stale", hide_stale and max(f.latest_captured_at for f in it.fares) < stale_before),
            # the day filter shows only the offers that depart on that local day (#709)
            (f"day {day}", day and it.legs and depart_day(it) != day),
        ) if hit}
        # an excluded mode or carrier hides each offer with one of its legs: each value is its own filter
        hides |= {f"excluded mode {m}" for m in exclude_mode if any(leg.mode == m for leg in it.legs)}
        hides |= {f"excluded carrier {c}" for c in exclude_carrier if any(_has_carrier(leg.carrier, c) for leg in it.legs)}
        tests.append(hides)
        hides_of[it.id] = hides
        if hides:
            # a candidate for the best hidden offer (#1454): never a "Hide", departed or all-gone row
            now_fares = [f for f in it.fares if f.id not in gone]
            if now_fares and not it.hidden and not departed.is_departed(it, departed_now):
                cand = (*row_cost(it, now_fares, places, weights, stale_before, rates, counts, fees), it, hides)
                if best_hidden is None or (cand[1].total, it.depart_at) < (best_hidden[1].total,
                                                                           best_hidden[2].depart_at):
                    best_hidden = cand
        if hides - {f"day {day}"}:
            continue  # a filter hides this row
        fare, cost = row_cost(it, fares, places, weights, stale_before, rates, counts, fees)
        all_rows.append((it, fare, cost))  # before the day filter: the days show all offers (#710)
        if hides:
            continue  # the day filter hides this row
        rows.append((it, fare, cost))
    def all_gone(r):
        return r[1].id in gone  # the main fare is gone only when all fares of the row are gone
    rows.sort(key=lambda r: (all_gone(r), r[2].total, r[0].depart_at))  # the default order and the tie order
    # a hidden or departed row gets no highlight (#200, #1391)
    shown = [r for r in rows if not r[0].hidden and not departed.is_departed(r[0], departed_now)
             and not all_gone(r)]  # a row with only gone fares gets no highlight (#1386)
    # no other shown offer is cheaper and faster (#1856): the price and the door-to-door minutes, not the weights
    pareto = pareto_ids([(r[0].id, r[2].price, door_minutes(r[0], places, weights)) for r in shown])
    if pareto_only:
        # "only these" (#1857): the marks stay as they are; each shown offer without a mark is hidden
        dropped = {r[0].id for r in shown if r[0].id not in pareto}
        for it_id in dropped:
            hides_of[it_id].add("only marked")
        rows = [r for r in rows if r[0].id not in dropped]
        shown = [r for r in shown if r[0].id not in dropped]
    # the routes of the shown rows before the route filter: the other routes still show (#2225)
    routes = trip_routes(shown)
    if route:
        def on_route(r):
            return route_value(tuple(name.casefold() for name in route_places(r[0]))) == route
        rows = [r for r in rows if on_route(r)]
        shown = [r for r in shown if on_route(r)]
    # the changes of a capture (#2329): the same sets as the counts of the captures page; another trip or an
    # unknown kind is no filter (P5)
    change_cap = session.get(Capture, capture) if capture is not None and change in ("new", "lower", "higher") else None
    change_line = None
    if change_cap is not None and change_cap.trip_id == trip_id:
        ids = getattr(capture_changes(session, [change_cap.id])[change_cap.id], change)
        rows = [r for r in rows if r[0].id in ids]
        shown = [r for r in shown if r[0].id in ids]
        change_line = (change_cap.captured_at, len(rows), change)
    badges = {}  # the highlights of the filtered rows (#113); a tie goes to the first row in the default order
    if shown:
        for name, key in (("best value", lambda r: r[2].total), ("cheapest", lambda r: r[2].price),
                          ("fastest", lambda r: r[0].duration_min)):
            badges.setdefault(min(shown, key=key)[0].id, []).append(name)
    # the price against the door-to-door hours of the shown offers (#1858)
    price_hours = pareto_chart([(r[0].id, r[0].mode_summary or "offer", r[2].price,
                                 door_minutes(r[0], places, weights)) for r in shown], pareto)
    if sort != "cost" or dir == "desc":
        rows.sort(key=SORT_KEYS[sort], reverse=dir == "desc")
    rows.sort(key=all_gone)  # stable: the rows with only gone fares after the current rows (#1386)
    rows.sort(key=lambda r: departed.is_departed(r[0], departed_now))  # the departed rows last (#1391)
    rows.sort(key=lambda r: not r[0].pinned)  # stable: the pinned rows first in every order, in their order (#199)
    view = {"sort": sort, "dir": dir, "mode": mode, "source": source, "badges": badges, "pareto": pareto, "price_hours": price_hours, "summary": trip_summary(shown), "best_modes": best_per_mode(shown), "show_hidden": show_hidden,
            "show_departed": show_departed, "departed_now": departed_now,
            "max_transfers": limit_transfers, "max_duration_min": limit_duration,
            "earliest_depart": earliest_depart, "latest_arrive": latest_arrive, "day": day,
            "modes": sorted(modes), "sources": sorted(sources), "carriers": sorted(carriers),
            "exclude_mode": exclude_mode, "exclude_carrier": exclude_carrier, "hide_stale": hide_stale,
            "pareto_only": pareto_only, "route": route}
    # the active weights (#230): a slider change or a sort keeps all values; night_hour_markup None is not sent
    query = {**{k: v for k, v in to_config(weights).items() if v is not None},
             **{k: MODE_HOUR_BLANK for k in MODE_HOUR_FIELDS if getattr(weights, k) is None},  # (#1568)
             "mode": mode, "source": source,
             **({"max_transfers": limit_transfers} if limit_transfers is not None else {}),
             **({"max_duration_min": limit_duration} if limit_duration is not None else {}),
             **({"earliest_depart": earliest_depart} if limit_depart is not None else {}),
             **({"latest_arrive": latest_arrive} if limit_arrive is not None else {}),
             **({"day": day} if day else {}),
             "exclude_mode": exclude_mode, "exclude_carrier": exclude_carrier}
    if show_hidden:
        query["show_hidden"] = True  # the sort links and the sliders keep it (#200)
    if show_departed:
        query["show_departed"] = True  # the sort links and the sliders keep it (#1391)
    if hide_stale:
        query["hide_stale"] = True  # the sort links keep it (#277)
    if pareto_only:
        query["pareto"] = True  # the sort links and the sliders keep it (#1857)
    if chosen is not None:
        query["profile"] = chosen.id  # a slider change or a sort keeps the profile (#231)
    # each route line links to this page with its key; "All routes" clears it (#2225)
    base = {**query, "sort": sort, "dir": dir}
    view["routes"] = [(r, route_value(r.key), "?" + urlencode({**base, "route": route_value(r.key)}, doseq=True))
                      for r in routes]
    view["all_routes_href"] = "?" + urlencode(base, doseq=True)
    if route:
        query["route"] = route  # the sort links and the sliders keep it (#2225)
    view["change_line"] = change_line
    if change_line:
        view["all_changes_href"] = "?" + urlencode({**query, "sort": sort, "dir": dir}, doseq=True)
        query["capture"], query["change"] = capture, change  # the sort links and the sliders keep it (#2329)
    # the break-even links re-rank this page with another hour value: the sort and the filters stay (#920)
    tradeoff = tradeoff_lines(rows, shown, source, places, weights, stale_before, rates,
                              trip_id, {**query, "sort": sort, "dir": dir}, counts, fees)  # #895
    context = {"joined": _joined_rows(session, trip_id), "trip": trip, "rows": rows, "weights": weights, "view": view, "sort_query": query, "sort_qs": urlencode(query, doseq=True), "format_breakdown": format_breakdown,
               "format_total": format_total, "bar_parts": bar_parts,
               "now": now, "stale_before": stale_before, "profiles": profiles, "active_profile_id": active_id,
               "rates": rates, "tradeoff": tradeoff, "gone_fares": gone_marks, "suspect_fares": suspect,
               "co2": {it.id: kg for it, *_ in rows if (kg := co2_kg(it, weights)) > 0},  # #1418
               "new_since": trip.viewed_at}  # the rows after the last full view are "new" (#1090)
    from app.models import ShareMark
    # the "Suits me" marks of the shared link (#1783): a chip and the note; no change of the score or the order (P2)
    context["share_marks"] = {m.itinerary_id: m for m in session.scalars(
        select(ShareMark).where(ShareMark.trip_id == trip_id))}
    context["search_urls"] = search_urls(session, itineraries)  # "Open search" (#2078)
    cards = fare_cards(session, itineraries)  # the discount cards of the fares (#1751)
    context["cards_warning"] = cards_warning(itineraries, cards, gone_marks, departed_now)
    context["card_label"] = lambda f: card_label(f, cards)
    if len(profiles) > 1:  # the best offer of each profile (#1211); one profile only: no section
        from app.profile_compare import best_by_profile
        context["profile_best"] = best_by_profile(session, trip)
    current = [r for r in all_rows if not all_gone(r)] or all_rows  # gone fares count only with no current one (#1386)
    from app.door import estimate_count, has_place_gap
    context["estimates"] = estimate_count(shown)  # the rows with an estimated part (#2053)
    context["estimate_places"] = has_place_gap(shown)
    context["days"] = day_summary(current, trip.date_from, trip.date_to,
                                  lambda it: depart_day(it) if it.legs else None)  # the days (#710)
    context["days"] = with_day_prices(context["days"], session.scalars(  # the day prices of bahn.de (#1198)
        select(DayPrice).where(DayPrice.trip_id == trip.id)).all())
    context["day_cover"] = day_cover(trip, itineraries, context["days"], stale_before,
                                       now.date(), sales_horizons(session))  # the searched sources (#2058, #2114)
    # the timeline of the shown rows (#815): one block per departure day; a bar links to its row
    context["timeline"] = timeline(rows, lambda it: depart_day(it) if it.legs else None)
    context["timeline_rows"] = {r[0].id: r for r in rows}
    # the links of the days strip (#711): all values of the query but the day
    context["days_qs"] = urlencode({k: v for k, v in query.items() if k != "day"}, doseq=True)
    # the seen price of each shown fare before mark_seen() changes it: the price changes of the rows (#1092)
    context["seen"] = {f.id: f.seen_price for r in rows for f in r[0].fares}
    best_direct = min((r[2].total for r in shown), default=None)
    context["hides_of"] = hides_of  # the filters that hide each offer: "Hide all" hides these (#1898)
    context["filtered"] = hidden_counts(tests, [  # the offers that each filter hides, in the order of the form (#1452)
        f"mode {mode}", f"source {source}", f"max transfers {limit_transfers}", f"max duration {limit_duration} min",
        f"depart after {earliest_depart}", f"arrive by {latest_arrive}",
        *(f"excluded mode {m}" for m in exclude_mode), *(f"excluded carrier {c}" for c in exclude_carrier),
        "hide stale", "only marked", f"day {day}"])
    # the transfer places of the offers of the page (#1460): only for a trip that is no part of a split
    context["via_places"] = [] if trip.split_of_id else via_places(itineraries, split_skip(trip))
    context["best_hidden"] = hidden_best(best_hidden, best_direct, query, sort, dir, trip_id)  # #1454
    # the link of each filter (#1453): the page with no such filter; the sort, the weights and the profile stay
    base = {**query, "sort": sort, "dir": dir}
    without = {f"mode {mode}": {"mode": ""}, f"source {source}": {"source": ""},
               f"max transfers {limit_transfers}": {"max_transfers": None},
               f"max duration {limit_duration} min": {"max_duration_min": None},
               f"depart after {earliest_depart}": {"earliest_depart": None},
               f"arrive by {latest_arrive}": {"latest_arrive": ""},  # empty: no arrive-by limit (#1296)
               "hide stale": {"hide_stale": None}, "only marked": {"pareto": None}, f"day {day}": {"day": None},
               **{f"excluded mode {m}": {"exclude_mode": [x for x in exclude_mode if x != m]} for m in exclude_mode},
               **{f"excluded carrier {c}": {"exclude_carrier": [x for x in exclude_carrier if x != c]}
                  for c in exclude_carrier}}
    context["filtered_qs"] = {label: urlencode({k: v for k, v in {**base, **change}.items() if v is not None},
                                               doseq=True) for label, change in without.items()}
    context["splits"] = split_sections(session, trip, weights, places, now, best_direct)  # #1179
    if request.headers.get("HX-Request"):  # a slider change: only the rows (htmx, #14)
        return templates.TemplateResponse(request, "trip_table.html", context)
    context["drops"] = trip_drops(session, trip_id)  # the drops since the last full view (#355)
    trend = trip_trend(session, trip_id)  # the cheapest price per day (#851): a chart for 2 or more days
    from app.trend_score import trip_score_trend  # the best effective cost per day (#2141): the second line
    scores = trip_score_trend(session, trip, weights, places, rates, counts, fees) if len(trend) >= 2 else []
    context["trend"] = trend_chart(trend, scores=scores) if len(trend) >= 2 else None
    from app.trend_score import best_changes  # the days on which another offer became the best (#2166)
    context["best_changes"] = best_changes(session, trip, weights, places, rates, counts, fees) if scores else []
    context["at_target"] = at_target(session, trip)  # the fares at or below the target price (#847)
    context["route_history"] = route_history(session, trip)  # the older trips on the same route (#1522)
    context["book_timing"] = book_timing(session, [trip.id] + [r.trip_id for r in context["route_history"]])  # #1916
    context["duplicates"] = duplicate_trips(session, trip)  # the other trips in planning of this journey (#1592)
    own = {it.id for it in trip.itineraries}  # the conflicts of the booked journeys of this trip (#1655)
    context["booked_conflicts"] = [c for it_id, found in conflicts(session, now).items() if it_id in own for c in found]
    mark_seen(session, trip_id)
    trip.viewed_at = now  # only the full view; an HX-Request keeps it (#1090)
    session.commit()
    context["journey"] = journey(session, trip, weights, places, now)
    context["round_grid"] = round_trip_grid(session, trip, context["days"], places, now)
    context["coverage"] = trip_coverage(session, trip, now.astimezone(timezone.utc).date(),
                                        sales_horizons(session))  # the search status and link per source (#318, #967)
    context["flash"] = request.session.pop("flash", None)
    context["share_link"] = request.session.pop("share_link", None)  # once after "Share" (#903)  # a message of the last action, for example an import
    context["share_ended"] = bool(trip.share_ends_on and datetime.now(timezone.utc).date() > trip.share_ends_on)  # #2027
    return templates.TemplateResponse(request, "trip.html", context)


def unfilter(query: dict, labels) -> dict:
    """The query without each filter of `labels` (the labels of `trip_page`, #1454)."""
    q = dict(query)
    for label in labels:
        if label.startswith("excluded mode "):
            q["exclude_mode"] = [m for m in q.get("exclude_mode", []) if m != label[14:]]
        elif label.startswith("excluded carrier "):
            q["exclude_carrier"] = [c for c in q.get("exclude_carrier", []) if c != label[17:]]
        elif label == "hide stale":
            q.pop("hide_stale", None)
        elif label == "only marked":
            q.pop("pareto", None)
        elif label.startswith("arrive by "):
            q["latest_arrive"] = ""  # an empty value is no limit; no value is the arrive-by time of the trip (#1296)
        else:
            key = {"mode": "mode", "source": "source", "max transfers": "max_transfers", "max duration": "max_duration_min",
                   "depart after": "earliest_depart", "day": "day"}
            for prefix, k in key.items():
                if label.startswith(prefix + " "):
                    q.pop(k, None)
                    if k in ("mode", "source"):
                        q[k] = ""
    return q


def hidden_best(best, best_direct, query, sort, dir, trip_id):
    """The text parts and the "Show it" link of the best offer that the filters hide (#1454), or None."""
    if best is None:
        return None
    fare, cost, it, labels = best
    leg0, leg1 = it.legs[0] if it.legs else None, it.legs[-1] if it.legs else None
    when = (leg0.depart_at + timedelta(minutes=leg0.depart_offset_min)).strftime("%H:%M") if leg0 else ""
    route = f"{leg0.from_name} → {leg1.to_name}" if leg0 else ""
    diff = None
    if best_direct is not None and cost.total != best_direct:
        d = best_direct - cost.total
        diff = f"€{abs(d):.2f} {'less' if d > 0 else 'more'} than the best shown offer"
    order = ["mode", "source", "max transfers", "max duration", "depart after", "arrive by", "excluded mode",
             "excluded carrier", "hide stale", "day"]
    by = sorted(labels, key=lambda l: next((i for i, p in enumerate(order) if l.startswith(p)), 99))
    link = f"/trips/{trip_id}?" + urlencode({**unfilter(query, labels), "sort": sort, "dir": dir}, doseq=True)
    return {"total": f"€{cost.total:.2f}", "when": when, "route": route, "source": fare.source,
            "by": ", ".join(by), "diff": diff, "link": f"{link}#it-{it.id}"}


def trip_view(**params) -> dict:
    """The query values of the trip page (sort, filters, weights) for a POST of a row action (#666)."""
    return params


trip_view.__signature__ = inspect.signature(trip_page).replace(parameters=[
    p for name, p in inspect.signature(trip_page).parameters.items() if name not in ("request", "trip_id", "session")])


def search_urls(session: Session, itineraries) -> dict[int, str]:
    """The page address of the capture of the newest price of each fare, in one query (#2078). Only an http or https
    address: a stored address is untrusted (P5)."""
    from app.models import Capture, FarePrice
    ids = [f.id for it in itineraries for f in it.fares]
    if not ids:
        return {}
    newest = (select(FarePrice.fare_id, FarePrice.capture_id,
                     func.row_number().over(partition_by=FarePrice.fare_id,
                                            order_by=(FarePrice.captured_at.desc(), FarePrice.id.desc())).label("n"))
              .where(FarePrice.fare_id.in_(ids)).subquery())
    rows = session.execute(select(newest.c.fare_id, Capture.page_url)
                           .join(Capture, Capture.id == newest.c.capture_id).where(newest.c.n == 1))
    return {fid: url for fid, url in rows if url and url.lower().startswith(("http://", "https://"))}


def _rows_or_redirect(request: Request, trip_id: int, session: Session, view: dict) -> Response:
    """An htmx row action gets the table with the new state, so the page keeps its scroll position (#666); a normal
    POST (no JavaScript) gets the redirect to the trip page."""
    if request.headers.get("HX-Request"):
        return trip_page(request, trip_id, session, **view)
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


def _tokens_page(request: Request, session: Session, new_token: str | None = None, code: int = 200,
                 error: str | None = None) -> HTMLResponse:
    tokens = session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())).all()
    server_url = str(request.base_url).rstrip("/")
    now = datetime.now(timezone.utc)
    unused_before = now - timedelta(days=90)
    # A token ends at 00:00 UTC of the day after its last day (#1847): show the last day.
    last_days = {t.id: (t.expires_at.astimezone(timezone.utc) - timedelta(days=1)).date()
                 for t in tokens if t.expires_at}
    return templates.TemplateResponse(request, "tokens.html", {"tokens": tokens, "new_token": new_token,
                                                               "server_url": server_url,
                                                               "unused_before": unused_before,
                                                               "now": now, "last_days": last_days,
                                                               "error": error,
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
                   destination_text=trip.origin_text, origin_alt_text=trip.destination_alt_text,
                   destination_alt_text=trip.origin_alt_text, travelers=trip.travelers, profile_id=trip.profile_id,
                   rail_pass_id=trip.rail_pass_id, return_of_id=trip.id)
        session.add(ret)
        session.commit()
    return RedirectResponse(f"/trips/{ret.id}/edit", status_code=303)


@router.post("/trips/{trip_id}/split", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def split_trip(request: Request, trip_id: int, session: Session = Depends(get_session)):
    """The two split trips of a trip via a place (#1177): A → X and X → B, with the dates, travelers and profile."""
    trip = _get_trip(session, trip_id)
    if trip.split_of_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a split trip cannot have split trips")
    place = str((await request.form()).get("via", "")).strip()[:200]
    if not place:
        values = {k: ("" if getattr(trip, k) is None else getattr(trip, k)) for k in FORM_FIELDS}
        return _form_page(request, values, [], trip_id, session, 422, split_error="Split via: enter a place.")
    origin, destination = trip.origin_text or "", trip.destination_text or ""
    for a, b in ((origin, place), (place, destination)):
        session.add(Trip(title=f"{a} → {b}"[:200], origin_text=a or None, destination_text=b or None,
                         date_from=trip.date_from, date_to=trip.date_to, travelers=trip.travelers,
                         profile_id=trip.profile_id, rail_pass_id=trip.rail_pass_id, split_of_id=trip.id))
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/next", dependencies=[Depends(require_login), Depends(verify_csrf)])
def make_next_trip(trip_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """The next part of a journey (#560): a new trip from the destination of the last trip of the chain."""
    journey = chain(_get_trip(session, trip_id))
    first, last = journey[0], journey[-1]
    new = Trip(title=f"{first.title[:180]} (part {len(journey) + 1})", origin_text=last.destination_text,
               destination_text=None, travelers=last.travelers, profile_id=last.profile_id, rail_pass_id=last.rail_pass_id,
               return_of_id=last.id)
    session.add(new)
    session.commit()
    return RedirectResponse(f"/trips/{new.id}/edit", status_code=303)


def _copy_of(trip: Trip, return_of_id: int | None = None) -> Trip:
    """A copy of a trip (#801): the places, travelers, profile, note and target price; no dates, offers or link
    (unless given)."""
    return Trip(title=f"{trip.title[:192]} (copy)", origin_text=trip.origin_text,
                destination_text=trip.destination_text, origin_alt_text=trip.origin_alt_text,
                destination_alt_text=trip.destination_alt_text, travelers=trip.travelers, profile_id=trip.profile_id,
                rail_pass_id=trip.rail_pass_id, notes=trip.notes, tags_text=trip.tags_text, target_price=trip.target_price, arrive_by=trip.arrive_by, leave_after=trip.leave_after,
                return_of_id=return_of_id)


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
                      overnight_min: int = Form(Weights.overnight_min, ge=0, le=1440),
                      overnight_cost: Decimal = Form(Weights.overnight_cost, ge=0, le=1000),
                      wait_hour_markup: Decimal = Form(Weights.wait_hour_markup, ge=0, le=100),
                      leave_hour_markup: Decimal = Form(Weights.leave_hour_markup, ge=0, le=200),  # (#2022)
                      night_hour_markup: Decimal | None = Form(None, ge=0, le=100),
                      short_transfer_min: int = Form(Weights.short_transfer_min, ge=0, le=240),
                      short_transfer_penalty: Decimal = Form(Weights.short_transfer_penalty, ge=0, le=1000),
                      station_change_min: int | None = Form(None, ge=0, le=240),
                      station_change_penalty: Decimal = Form(Weights.station_change_penalty, ge=0, le=1000),
                      no_fallback_penalty: Decimal = Form(Weights.no_fallback_penalty, ge=0, le=1000),
                      train_markup: Decimal = Form(Weights.train_markup, ge=-1000, le=1000),
                      bus_markup: Decimal = Form(Weights.bus_markup, ge=-1000, le=1000),
                      flight_markup: Decimal = Form(Weights.flight_markup, ge=-1000, le=1000),
                      ferry_markup: Decimal = Form(Weights.ferry_markup, ge=-1000, le=1000),
                      co2_price_kg: Decimal = Form(Weights.co2_price_kg, ge=0, le=10),
                      co2_train_kg_h: Decimal = Form(Weights.co2_train_kg_h, ge=0, le=1000),
                      co2_bus_kg_h: Decimal = Form(Weights.co2_bus_kg_h, ge=0, le=1000),
                      co2_flight_kg_h: Decimal = Form(Weights.co2_flight_kg_h, ge=0, le=1000),
                      co2_ferry_kg_h: Decimal = Form(Weights.co2_ferry_kg_h, ge=0, le=1000),
                      flex_non_refundable: Decimal = Form(Weights.flex_non_refundable, ge=-1000, le=1000),
                      flex_partly_refundable: Decimal = Form(Weights.flex_partly_refundable, ge=-1000, le=1000),
                      flex_flexible: Decimal = Form(Weights.flex_flexible, ge=-1000, le=1000),
                      first_class_hour: Decimal = Form(Weights.first_class_hour, ge=-1000, le=1000),
                      self_transfer_penalty: Decimal = Form(Weights.self_transfer_penalty, ge=0, le=1000),
                      reservation_fee: Decimal = Form(Weights.reservation_fee, ge=0, le=1000),
                      currency_fee_pct: Decimal = Form(Weights.currency_fee_pct, ge=0, le=10),  # (#1993)
                      stale_hours: int = Form(Weights.stale_hours, ge=1, le=720),
                      stale_penalty: Decimal = Form(Weights.stale_penalty, ge=0, le=1000),
                      hour_tier1_after_min: int = Form(Weights.hour_tier1_after_min, ge=0, le=2880),
                      hour_tier1_markup: Decimal = Form(Weights.hour_tier1_markup, ge=0, le=100),
                      hour_tier2_after_min: int = Form(Weights.hour_tier2_after_min, ge=0, le=2880),
                      hour_tier2_markup: Decimal = Form(Weights.hour_tier2_markup, ge=0, le=100),
                      carrier1_name: str = Form(Weights.carrier1_name, max_length=50),
                      carrier1_markup: Decimal = Form(Weights.carrier1_markup, ge=-1000, le=1000),
                      carrier2_name: str = Form(Weights.carrier2_name, max_length=50),
                      carrier2_markup: Decimal = Form(Weights.carrier2_markup, ge=-1000, le=1000),
                      carrier3_name: str = Form(Weights.carrier3_name, max_length=50),
                      carrier3_markup: Decimal = Form(Weights.carrier3_markup, ge=-1000, le=1000),
                      weekday1_markup: Decimal = Form(Weights.weekday1_markup, ge=-1000, le=1000),
                      weekday2_markup: Decimal = Form(Weights.weekday2_markup, ge=-1000, le=1000),
                      weekday3_markup: Decimal = Form(Weights.weekday3_markup, ge=-1000, le=1000),
                      weekday4_markup: Decimal = Form(Weights.weekday4_markup, ge=-1000, le=1000),
                      weekday5_markup: Decimal = Form(Weights.weekday5_markup, ge=-1000, le=1000),
                      weekday6_markup: Decimal = Form(Weights.weekday6_markup, ge=-1000, le=1000),
                      weekday7_markup: Decimal = Form(Weights.weekday7_markup, ge=-1000, le=1000),
                      transfer_place1_name: str = Form(Weights.transfer_place1_name, max_length=100),
                      transfer_place1_markup: Decimal = Form(Weights.transfer_place1_markup, ge=-1000, le=1000),
                      transfer_place2_name: str = Form(Weights.transfer_place2_name, max_length=100),
                      transfer_place2_markup: Decimal = Form(Weights.transfer_place2_markup, ge=-1000, le=1000),
                      transfer_place3_name: str = Form(Weights.transfer_place3_name, max_length=100),
                      transfer_place3_markup: Decimal = Form(Weights.transfer_place3_markup, ge=-1000, le=1000),
                      transfer_place1_min: int | None = Form(None, ge=0, le=240),
                      transfer_place2_min: int | None = Form(None, ge=0, le=240),
                      transfer_place3_min: int | None = Form(None, ge=0, le=240),
                      train_hour_markup: Decimal | None = Form(None, ge=0, le=100),  # (#1567)
                      bus_hour_markup: Decimal | None = Form(None, ge=0, le=100),  # (#1567)
                      flight_hour_markup: Decimal | None = Form(None, ge=0, le=100),  # (#1567)
                      ferry_hour_markup: Decimal | None = Form(None, ge=0, le=100),  # (#1567)
                      transfer_wait_hour_markup: Decimal | None = Form(None, ge=0, le=100),  # (#2220)
                      later_transfer_markup: Decimal | None = Form(None, ge=0, le=100),  # (#2302)
                      work_hour_markup: Decimal | None = Form(None, ge=0, le=100),  # (#2332)
                      work_hour_start: int = Form(9, ge=0, le=23),  # (#2332)
                      work_hour_end: int = Form(17, ge=1, le=24),  # (#2332)
                      night_seat_adjust: Decimal | None = Form(None, ge=-1000, le=1000),  # (#1808)
                      night_couchette_adjust: Decimal | None = Form(None, ge=-1000, le=1000),  # (#1808)
                      night_sleeper_adjust: Decimal | None = Form(None, ge=-1000, le=1000),  # (#1808)
                      session: Session = Depends(get_session)) -> RedirectResponse:
    """Store the present weights of the trip page as a named profile (#229); the same ranges as `trip_page`."""
    if session.get(Trip, trip_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    weights = Weights(hour_markup=hour_markup, transfer_markup=transfer_markup,
                      airport_before_min=airport_before_min, airport_after_min=airport_after_min,
                      baggage_fee=baggage_fee, early_limit=early_limit, late_limit=late_limit,
                      time_window_penalty=time_window_penalty, night_start=night_start, night_end=night_end,
                      night_min=night_min, night_adjust=night_adjust, night_hour_markup=night_hour_markup,
                      overnight_min=overnight_min, overnight_cost=overnight_cost, wait_hour_markup=wait_hour_markup,
                      leave_hour_markup=leave_hour_markup,
                      short_transfer_min=short_transfer_min, short_transfer_penalty=short_transfer_penalty,
                      station_change_min=station_change_min, station_change_penalty=station_change_penalty,
                      no_fallback_penalty=no_fallback_penalty,
                      train_markup=train_markup, bus_markup=bus_markup, flight_markup=flight_markup,
                      ferry_markup=ferry_markup, co2_price_kg=co2_price_kg, co2_train_kg_h=co2_train_kg_h,
                      co2_bus_kg_h=co2_bus_kg_h, co2_flight_kg_h=co2_flight_kg_h, co2_ferry_kg_h=co2_ferry_kg_h,
                      flex_non_refundable=flex_non_refundable,
                      flex_partly_refundable=flex_partly_refundable, flex_flexible=flex_flexible,
                      first_class_hour=first_class_hour,
                      self_transfer_penalty=self_transfer_penalty, reservation_fee=reservation_fee,
                      currency_fee_pct=currency_fee_pct, stale_hours=stale_hours,
                      stale_penalty=stale_penalty, hour_tier1_after_min=hour_tier1_after_min,
                      hour_tier1_markup=hour_tier1_markup, hour_tier2_after_min=hour_tier2_after_min,
                      hour_tier2_markup=hour_tier2_markup,
                      carrier1_name=carrier1_name, carrier1_markup=carrier1_markup,
                      carrier2_name=carrier2_name, carrier2_markup=carrier2_markup,
                      carrier3_name=carrier3_name, carrier3_markup=carrier3_markup,
                      weekday1_markup=weekday1_markup, weekday2_markup=weekday2_markup, weekday3_markup=weekday3_markup,
                      weekday4_markup=weekday4_markup, weekday5_markup=weekday5_markup, weekday6_markup=weekday6_markup, weekday7_markup=weekday7_markup,
                      transfer_place1_name=transfer_place1_name, transfer_place1_markup=transfer_place1_markup,
                      transfer_place2_name=transfer_place2_name, transfer_place2_markup=transfer_place2_markup,
                      transfer_place3_name=transfer_place3_name, transfer_place3_markup=transfer_place3_markup,
                      transfer_place1_min=transfer_place1_min, transfer_place2_min=transfer_place2_min,
                      transfer_place3_min=transfer_place3_min,
                      train_hour_markup=train_hour_markup, bus_hour_markup=bus_hour_markup,
                      flight_hour_markup=flight_hour_markup, ferry_hour_markup=ferry_hour_markup,
                      transfer_wait_hour_markup=transfer_wait_hour_markup,
                      later_transfer_markup=later_transfer_markup,
                      work_hour_markup=work_hour_markup, work_hour_start=work_hour_start,
                      work_hour_end=work_hour_end,
                      night_seat_adjust=night_seat_adjust, night_couchette_adjust=night_couchette_adjust,
                      night_sleeper_adjust=night_sleeper_adjust)
    save_profile(session, name.strip(), weights)
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


# The ranges of the weights in a form (#1013): the same as `weight_query()` and `save_profile_page()`.
# (low, high) for a number, None for a time of day.
WEIGHT_RANGES = {
    "hour_markup": (0, 100), "transfer_markup": (0, 100), "airport_before_min": (0, 1440),
    "airport_after_min": (0, 1440), "baggage_fee": (0, 1000), "early_limit": None, "late_limit": None,
    "time_window_penalty": (0, 1000), "night_start": None, "night_end": None, "night_min": (0, 1440),
    "night_adjust": (-1000, 1000), "overnight_min": (0, 1440), "overnight_cost": (0, 1000), "wait_hour_markup": (0, 100),
    "leave_hour_markup": (0, 200),
    "night_hour_markup": (0, 100), "short_transfer_min": (0, 240),
    "short_transfer_penalty": (0, 1000), "station_change_min": (0, 240), "station_change_penalty": (0, 1000),
    "no_fallback_penalty": (0, 1000),
    "train_markup": (-1000, 1000), "bus_markup": (-1000, 1000),
    "flight_markup": (-1000, 1000), "ferry_markup": (-1000, 1000), "flex_non_refundable": (-1000, 1000),
    "co2_price_kg": (0, 10), "co2_train_kg_h": (0, 1000), "co2_bus_kg_h": (0, 1000),
    "co2_flight_kg_h": (0, 1000), "co2_ferry_kg_h": (0, 1000),
    "flex_partly_refundable": (-1000, 1000), "flex_flexible": (-1000, 1000), "first_class_hour": (-1000, 1000),
    "self_transfer_penalty": (0, 1000), "reservation_fee": (0, 1000), "currency_fee_pct": (0, 10), "stale_hours": (1, 720), "stale_penalty": (0, 1000),
    "hour_tier1_after_min": (0, 2880), "hour_tier1_markup": (0, 100), "hour_tier2_after_min": (0, 2880),
    "hour_tier2_markup": (0, 100),
    "carrier1_markup": (-1000, 1000), "carrier2_markup": (-1000, 1000), "carrier3_markup": (-1000, 1000),
    "weekday1_markup": (-1000, 1000), "weekday2_markup": (-1000, 1000), "weekday3_markup": (-1000, 1000), "weekday4_markup": (-1000, 1000), "weekday5_markup": (-1000, 1000), "weekday6_markup": (-1000, 1000), "weekday7_markup": (-1000, 1000),
    "transfer_place1_markup": (-1000, 1000), "transfer_place2_markup": (-1000, 1000),
    "transfer_place3_markup": (-1000, 1000),  # (#1850)
    "transfer_place1_min": (0, 240), "transfer_place2_min": (0, 240), "transfer_place3_min": (0, 240),  # (#2073)
    "train_hour_markup": (0, 100), "bus_hour_markup": (0, 100), "flight_hour_markup": (0, 100),
    "ferry_hour_markup": (0, 100),  # (#1567)
    "transfer_wait_hour_markup": (0, 100),  # (#2220)
    "later_transfer_markup": (0, 100),  # (#2302)
    "work_hour_markup": (0, 100), "work_hour_start": (0, 23), "work_hour_end": (1, 24),  # (#2332)
    "night_seat_adjust": (-1000, 1000), "night_couchette_adjust": (-1000, 1000),
    "night_sleeper_adjust": (-1000, 1000),  # (#1808)
}


def form_weights(form) -> tuple[Weights, str | None]:
    """The `Weights` of a profile form (#1013) and the first error. A missing or empty field takes the `Weights`
    default (`night_hour_markup`: None, the same as the hour markup)."""
    values = {}
    for f in dataclasses.fields(Weights):
        raw = (form.get(f.name) or "").strip()
        if not raw:
            continue
        if isinstance(f.default, str):  # a carrier name (#1531): up to 50 characters; a transfer place: 100 (#1851)
            limit = 100 if f.name.startswith("transfer_place") else 50
            if len(raw) > limit:
                return Weights(), f"{f.name}: the name is longer than {limit} characters; nothing changed."
            values[f.name] = raw
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
                  error: str | None = None, code: int = 200, fit=None) -> HTMLResponse:
    return templates.TemplateResponse(request, "profile_edit.html", {"profile": profile, "name": name,
                                      "weights": weights, "error": error, "fit": fit}, status_code=code)


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
    weights = from_config(profile.config_json)
    return _profile_form(request, profile, profile.name, weights, fit=_hour_fit(session, weights))


def _hour_fit(session: Session, weights: Weights):
    """(low, high, count, total) of the bookings at these weights, or None (#1711)."""
    from app.calibrate import best_fit, booking_intervals
    places = session.scalars(select(AccessTime)).all()
    rows = booking_intervals(session, weights, places, load_rates(session), load_fees(session))
    return best_fit(iv for _, iv in rows)


def fit_hour_value(fit) -> Decimal:
    """The middle of a closed interval, else its one end; in cents and inside 0 to 100 (#1711)."""
    low, high = fit[0], fit[1]
    v = (low + high) / 2 if low is not None and high is not None else (low if low is not None else high)
    return min(max(v, Decimal("0")), Decimal("100")).quantize(Decimal("0.01"))


@router.post("/profiles/{profile_id}/hour-value", dependencies=[Depends(require_login), Depends(verify_csrf)])
def use_hour_value_page(profile_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    profile = session.get(ScoreProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    weights = from_config(profile.config_json)
    fit = _hour_fit(session, weights)  # again on the server: the form sends no value
    if fit is not None:
        update_profile(session, profile_id, profile.name,
                       dataclasses.replace(weights, hour_markup=fit_hour_value(fit)))
    return RedirectResponse(f"/profiles/{profile_id}", status_code=303)


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
    it.booked_fare_id = it.booked_price = it.booked_currency = it.booked_at = None
    it.cancelled_at = it.refund_price = it.booking_code = None
    it.cancel_by = it.cancel_by_offset_min = None
    if it.booked:
        keep_paid_fare(session, it)
    session.commit()
    return _rows_or_redirect(request, trip_id, session, view)


def keep_paid_fare(session: Session, it: Itinerary) -> None:
    """Keep the paid fare: the main fare with the weights of the trip (#1146)."""
    if not it.fares:
        return
    now = datetime.now(timezone.utc)
    weights, _ = resolve_weights(session, it.trip, {}, None)
    places = trip_places(session, it.trip)  # (#2109)
    fare, _ = row_cost(it, it.fares, places, weights, now - timedelta(hours=weights.stale_hours),
                       load_rates(session), fare_travelers(session, [it]), load_fees(session))
    it.booked_fare_id, it.booked_price, it.booked_currency, it.booked_at = fare.id, fare.latest_price, fare.currency, now


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


PAID_PRICE_MAX = Decimal("100000")  # the paid price is below this (#1148)


BOOKING_CODE_MAX = 40  # the length of the booking code column (#1716)
DELAY_MAX_MIN = 1440  # the arrival delay is 0 to this number of minutes (#1691)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/cancel-by",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_cancel_by(trip_id: int, itinerary_id: int, cancel_by: str = Form(""),
                   session: Session = Depends(get_session)) -> RedirectResponse:
    """The owner stores the last local time to cancel a booked journey (#2311), on the clock of the departure of the
    first leg. A blank clears the time; a value that is not a date and time is 422 and stores nothing."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    if not it.booked and it.cancelled_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the itinerary is not booked")
    text = cancel_by.strip()
    if not text:
        it.cancel_by = it.cancel_by_offset_min = None
    else:
        try:
            naive = datetime.strptime(text, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the cancel time is not a date and time")
        offset = it.legs[0].depart_offset_min if it.legs else 0
        aware = naive.replace(tzinfo=timezone(timedelta(minutes=offset)))
        it.cancel_by = aware.astimezone(timezone.utc)
        it.cancel_by_offset_min = offset
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/booking-code",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_booking_code(trip_id: int, itinerary_id: int, code: str = Form(""),
                      session: Session = Depends(get_session)) -> RedirectResponse:
    """The owner stores the booking code of a booked or cancelled journey (#1716): at most 40 characters. A blank
    clears the code; a longer code is 422 and stores nothing."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    if not it.booked and it.cancelled_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the itinerary is not booked")
    text = code.strip()
    if len(text) > BOOKING_CODE_MAX:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"the booking code has more than {BOOKING_CODE_MAX} characters")
    it.booking_code = text or None
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/delay",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_delay(trip_id: int, itinerary_id: int, minutes: str = Form(""),
               session: Session = Depends(get_session)) -> RedirectResponse:
    """The owner stores the arrival delay of a booked journey that arrived (#1691): a whole number of 0 to 1440
    minutes. A blank clears the delay; a bad value is 422 and stores nothing."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    if not it.booked:
        raise HTTPException(status.HTTP_409_CONFLICT, "the itinerary is not booked")
    if it.arrive_at > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_409_CONFLICT, "the journey did not arrive yet")
    text = minutes.strip()
    if not text:
        it.delay_min = None
    elif not re.fullmatch(r"[0-9]{1,4}", text) or int(text) > DELAY_MAX_MIN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the delay needs a whole number of 0 to 1440")
    else:
        it.delay_min = int(text)
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/paid",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_paid(trip_id: int, itinerary_id: int, fare_id: int = Form(...), price: str = Form(...),
              session: Session = Depends(get_session)) -> RedirectResponse:
    """The owner corrects the paid fare and price of a booked row (#1148): a fare of this itinerary, and a price of
    0 to below 100000 with at most 2 decimals. A blank or a bad price is 422 and stores nothing."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    if not it.booked:
        raise HTTPException(status.HTTP_409_CONFLICT, "the itinerary is not booked")
    try:
        value = Decimal(price.strip())
    except InvalidOperation:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the price is not a number") from None
    if not value.is_finite() or value < 0 or value >= PAID_PRICE_MAX or value.as_tuple().exponent < -2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the price needs 0 to 99999.99 with 2 decimals")
    fare = next((f for f in it.fares if f.id == fare_id), None)
    if fare is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"fare {fare_id} is not a fare of this itinerary")
    it.booked_fare_id, it.booked_price, it.booked_currency = fare.id, value, fare.currency
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/cancel",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def cancel_booking(trip_id: int, itinerary_id: int, refund: str = Form(""),
                   session: Session = Depends(get_session)) -> RedirectResponse:
    """The owner cancels a booked journey with a refund (#1685): 0 to the paid price (0 with no paid price), at most
    2 decimals, blank = 0. The paid fields stay; a bad refund is 422 and stores nothing."""
    it = session.get(Itinerary, itinerary_id)
    if it is None or it.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    if not it.booked:
        raise HTTPException(status.HTTP_409_CONFLICT, "the itinerary is not booked")
    try:
        value = Decimal(refund.strip() or "0")
    except InvalidOperation:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the refund is not a number") from None
    limit = it.booked_price if it.booked_price is not None else Decimal("0")
    if not value.is_finite() or value < 0 or value > limit or value.as_tuple().exponent < -2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"the refund needs 0 to {limit} with 2 decimals")
    it.booked, it.cancelled_at, it.refund_price = False, datetime.now(timezone.utc), value
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


def _joined_rows(session: Session, trip_id: int) -> dict[int, list[int]]:
    """The ids of the rows that are joined into each row of the trip (#2145)."""
    joined: dict[int, list[int]] = {}
    for b_id, a_id in session.execute(select(Itinerary.id, Itinerary.merged_into_id).where(
            Itinerary.trip_id == trip_id, Itinerary.merged_into_id.is_not(None)).order_by(Itinerary.id)):
        joined.setdefault(a_id, []).append(b_id)
    return joined


@router.post("/trips/{trip_id}/itineraries/{itinerary_id}/split/{joined_id}",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def split_journey(request: Request, trip_id: int, itinerary_id: int, joined_id: int,
                  session: Session = Depends(get_session), view: dict = Depends(trip_view)) -> Response:
    """"Not the same journey" (#2145): split a joined row from its row, the reverse of "Same journey"."""
    a, b = session.get(Itinerary, itinerary_id), session.get(Itinerary, joined_id)
    if a is None or b is None or a.trip_id != trip_id or b.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"an itinerary is not in trip {trip_id}")
    try:
        split(session, a, b)
        session.commit()
        request.session["flash"] = "The row is split into 2 rows."
    except JoinError as e:
        session.rollback()
        request.session["flash"] = f"Not split: {e}."
    return _rows_or_redirect(request, trip_id, session, view)


@router.post("/trips/{trip_id}/itineraries/bulk",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def bulk_hide_or_pin(request: Request, trip_id: int, action: str = Query(""), it: list[int] = Form([]),
                     session: Session = Depends(get_session), view: dict = Depends(trip_view)) -> Response:
    """Hide or pin all the ticked offers of the trip (#1897). The action comes in the query of the button's
    formaction, the CSRF token in the button's own value (a button sends only its own name and value). All ids are
    checked before any change: an id of another trip gives 404 and changes nothing."""
    if action not in ("hide", "pin", "join"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action must be hide, pin or join")
    rows = [session.get(Itinerary, itinerary_id) for itinerary_id in it]
    if any(row is None or row.trip_id != trip_id for row in rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"an itinerary is not in trip {trip_id}")
    if action == "join":  # "Same journey" (#2145): the first ticked row of the table order is A
        if len(rows) != 2:
            request.session["flash"] = "Select exactly 2 rows for \u201cSame journey\u201d. Nothing changed."
        else:
            try:
                join(session, rows[0], rows[1])
                session.commit()
                request.session["flash"] = "The 2 rows are joined into one row."
            except JoinError as e:
                session.rollback()
                request.session["flash"] = f"Not joined: {e}."
        return _rows_or_redirect(request, trip_id, session, view)
    for row in rows:
        if action == "hide":
            row.hidden = True
        else:
            row.pinned = True
    session.commit()
    return _rows_or_redirect(request, trip_id, session, view)


@router.post("/trips/{trip_id}/itineraries/hide-filtered",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def hide_filtered(request: Request, trip_id: int, session: Session = Depends(get_session),
                  view: dict = Depends(trip_view)) -> Response:
    """"Hide all" of the filter line (#1898): hides each offer that a filter of the page hides, with the filters of
    the request (the query of the button's formaction). The page is built as for a GET, so the rows are the same
    ones that the line counts."""
    filtered_page = trip_page(request, trip_id, session, **view)
    ids = [it_id for it_id, labels in filtered_page.context["hides_of"].items() if labels]
    if ids:
        for row in session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.id.in_(ids))):
            row.hidden = True
        session.commit()
    return _rows_or_redirect(request, trip_id, session, view)


@router.get("/tokens", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def tokens_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _tokens_page(request, session)


@router.post("/tokens", response_class=HTMLResponse, dependencies=[Depends(require_login), Depends(verify_csrf)])
def new_token(request: Request, name: str = Form(""), expires_on: str = Form(""),
              session: Session = Depends(get_session)) -> HTMLResponse:
    name = name.strip()[:100]
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a token needs a name")
    ends_at = None
    if expires_on.strip():  # a blank field is no end date (#1847)
        try:
            last_day = datetime.strptime(expires_on.strip(), "%Y-%m-%d").date()
        except ValueError:
            return _tokens_page(request, session, code=422, error="The end date is not a valid date.")
        if last_day < datetime.now(timezone.utc).date():
            return _tokens_page(request, session, code=422,
                                error="The end date is before today. No token was made.")
        ends_at = datetime.combine(last_day + timedelta(days=1), time(0), tzinfo=timezone.utc)
    # The value shows only in this response; the database keeps only its hash (P5).
    return _tokens_page(request, session, create_token(session, name, expires_at=ends_at))


@router.post("/tokens/{token_id}/revoke", dependencies=[Depends(require_login), Depends(verify_csrf)])
def revoke(token_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    revoke_token(session, token_id)
    return RedirectResponse("/tokens", status_code=303)


PLACE_KINDS = ("access", "egress")


@router.get("/places", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def places_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    places = session.scalars(select(AccessTime).order_by(AccessTime.kind, AccessTime.place_text, AccessTime.id)).all()
    return templates.TemplateResponse(request, "places.html", {"places": places, "kinds": PLACE_KINDS})


def _place_values(place_text: str, kind: str, minutes: str, cost: str) -> tuple[str, int, Decimal]:
    """The checked place, minutes and cost of a place form (#97), else 422."""
    place_text = place_text.strip()
    try:
        minutes_value = int(minutes)
        cost_value = Decimal(cost.strip() or "0")
    except (ValueError, InvalidOperation):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "minutes and cost must be numbers")
    if (not place_text or len(place_text) > 200 or kind not in PLACE_KINDS or minutes_value < 0
            or not cost_value.is_finite() or cost_value < 0 or cost_value >= Decimal("100000000")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a place needs a text, a kind and values >= 0")
    return place_text, minutes_value, cost_value.quantize(Decimal("0.01"))


@router.post("/places", dependencies=[Depends(require_login), Depends(verify_csrf)])
def new_place(place_text: str = Form(""), kind: str = Form(""), minutes: str = Form(""), cost: str = Form(""),
              session: Session = Depends(get_session)) -> RedirectResponse:
    place_text, minutes_value, cost_value = _place_values(place_text, kind, minutes, cost)
    session.add(AccessTime(place_text=place_text, kind=kind, minutes=minutes_value, cost=cost_value))
    session.commit()
    return RedirectResponse("/places", status_code=303)


def _place_key(text_: str) -> str:
    return text_.strip().lower()


def _trip_places(session: Session, trip_id: int) -> list[tuple[TripAccessTime, AccessTime | None]]:
    """The overrides of a trip (#2110), each with the global place of the same kind and place key."""
    own = session.scalars(select(TripAccessTime).where(TripAccessTime.trip_id == trip_id)
                          .order_by(TripAccessTime.kind, TripAccessTime.place_text, TripAccessTime.id)).all()
    shared = {(p.kind, _place_key(p.place_text)): p for p in session.scalars(select(AccessTime))}
    return [(p, shared.get((p.kind, _place_key(p.place_text)))) for p in own]


@router.post("/trips/{trip_id}/places", dependencies=[Depends(require_login), Depends(verify_csrf)])
def new_trip_place(trip_id: int, place_text: str = Form(""), kind: str = Form(""), minutes: str = Form(""),
                   cost: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    _get_trip(session, trip_id)
    place_text, minutes_value, cost_value = _place_values(place_text, kind, minutes, cost)
    row = next((p for p, _ in _trip_places(session, trip_id)
                if p.kind == kind and _place_key(p.place_text) == _place_key(place_text)), None)
    if row is None:  # an override of the same kind and place key changes the row (#2110)
        row = TripAccessTime(trip_id=trip_id, kind=kind)
        session.add(row)
    row.place_text, row.minutes, row.cost = place_text, minutes_value, cost_value
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}/edit", status_code=303)


@router.post("/trips/{trip_id}/places/{place_id}/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_trip_place(trip_id: int, place_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    place = session.get(TripAccessTime, place_id)
    if place is None or place.trip_id != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such place of this trip")
    session.delete(place)
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}/edit", status_code=303)


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


def fee_sources() -> list[tuple[str, str]]:
    """Each source that can have a fee (#1142): the parsers and `manual`, with the name of the search links."""
    from app.parsers import parser_classes
    from app.search_links import load_sources

    names = {v.get("source"): v.get("name") for v in load_sources().values() if isinstance(v, dict)}
    return [(s, names.get(s) or s) for s in [*parser_classes(), "manual"]]


def _fees_page(request: Request, session: Session, error: str | None = None, code: int = 200) -> HTMLResponse:
    fees = load_fees(session)
    rows = [(s, name, fees.get(s, Decimal("0"))) for s, name in fee_sources()]
    return templates.TemplateResponse(request, "fees.html", {"rows": rows, "error": error}, status_code=code)


@router.get("/fees", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def fees_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return _fees_page(request, session)


@router.post("/fees", response_model=None, dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_fee(request: Request, source: str = Form(""), amount: str = Form(""),
             session: Session = Depends(get_session)) -> HTMLResponse | RedirectResponse:
    """Set the booking fee of one source; a fee of 0 deletes the row (#1142)."""
    source = source.strip()
    if source not in dict(fee_sources()):
        return _fees_page(request, session, "The source is not known.", 422)
    try:
        value = Decimal(amount.strip())
    except InvalidOperation:
        value = None
    if (value is None or not value.is_finite() or value < 0 or value > Decimal("1000")
            or value.as_tuple().exponent < -2):
        return _fees_page(request, session, "The fee must be a number from 0 to 1000 with at most 2 decimals.", 422)
    row = session.get(SourceFee, source)
    if value == 0:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(SourceFee(source=source, amount=value, updated_at=datetime.now(timezone.utc)))
    else:
        row.amount, row.updated_at = value, datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse("/fees", status_code=303)


def _backup_check(session: Session, newest: tuple[datetime, int] | None) -> dict | None:
    """The result of the check of the newest backup (#1491). The daily loop writes the setting `backup_check` (#1490).

    The stamp at the start of the file name gives its time: a check of another file gives "none". A broken value gives "none".
    """
    try:
        data = json.loads(setting(session, "backup_check"))
        checked = datetime.strptime(str(data["file"]).split("-", 1)[0], STAMP_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"state": "none"} if newest is not None else None
    # A failed check renames its file to `*.failed`, so the newest `*.dump` is an older good one (or none) (#1516).
    if "error" in data and (newest is None or checked >= newest[0]):
        return {"state": "failed", "at": str(data.get("at", "")), "error": str(data["error"])}
    if newest is None:
        return None
    if checked != newest[0]:
        return {"state": "none"}
    if isinstance(data.get("tables"), int):
        return {"state": "ok", "tables": data["tables"]}
    return {"state": "none"}


def version_card(session: Session) -> dict:
    """The card "Version" (#1738): the commit with its link, the build time and the database revision."""
    sha = os.environ.get("GIT_SHA", "dev")
    repo = get_settings().issues_url.removesuffix("/issues/new")
    built = _built()
    try:
        built_text = datetime.strptime(built, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        built_text = built
    current, head = revisions(session)
    return {"sha": sha, "link": f"{repo}/commit/{sha}" if sha != "dev" else "", "built": built_text,
            "current": current or "none", "head": head or "none", "pending": current != head}


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def settings_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """General: the capture retention period and the state of the backups (#925)."""
    newest = newest_backup(Path(os.environ.get("BACKUP_DIR", "/backups")))
    days = retention_days(session)
    return templates.TemplateResponse(request, "settings.html", {"backup": newest,
                                                                     "version": version_card(session),
                                                                     "backup_check": _backup_check(session, newest),
                                                                 "backup_old": newest is not None and
                                                                 datetime.now(timezone.utc) - newest[0] > BACKUP_MAX_AGE,
                                                                 "retention_days": days,
                                                                 "storage": storage_use(session, days, datetime.now(timezone.utc)),
                                                                 "max_days": MAX_RETENTION_DAYS,
                                                                 "flash": request.session.pop("flash", None),
                                                                 "totp": totp_state(request, session),
                                                                 "passkeys": passkeys.listing(session),
                                                                 "logins": login_log.recent(session),
                                                                 "metrics_token": request.session.pop("metrics_token", None),
                                                                 "metrics_on": session.get(Setting, "metrics_token_hash") is not None,
                                                                 "place_names": session.scalars(select(PlaceName).order_by(PlaceName.city, PlaceName.id)).all(),
                                                                 "builtin_places": ALIASES,
                                                                 "place_error": request.session.pop("place_error", None)})


def _place_name_error(session: Session, city: str, name: str) -> str | None:
    """The reason to reject a place name, or None (#2217, P5)."""
    for label, value in (("City", city), ("Name", name)):
        if not 1 <= len(value) <= 60:
            return f"{label} must have 1 to 60 characters."
    known = {fold(n) for key, local in place_aliases(session).items() for n in (key, *local)}
    if fold(name) in known:
        return f"The name {name} is already a place name."
    return None


@router.post("/settings/place-names", dependencies=[Depends(require_login), Depends(verify_csrf)])
def add_place_name(request: Request, city: str = Form(""), name: str = Form(""),
                   session: Session = Depends(get_session)) -> RedirectResponse:
    """Add a place name of the owner (#2217)."""
    city, name = city.strip(), name.strip()
    error = _place_name_error(session, city, name)
    if error:
        request.session["place_error"] = error
    else:
        session.add(PlaceName(city=city, name=name))
        session.commit()
    return RedirectResponse("/settings#place-names", status_code=303)


@router.post("/settings/place-names/{place_id}/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def delete_place_name(place_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    """Delete a place name of the owner (#2217)."""
    row = session.get(PlaceName, place_id)
    if row is not None:
        session.delete(row)
        session.commit()
    return RedirectResponse("/settings#place-names", status_code=303)


def totp_state(request: Request, session: Session) -> dict:
    """The state of the card "Second login step" (#1314)."""
    new = request.session.get(NEW_TOTP_KEY)
    return {"on": session.get(Setting, TOTP_SECRET) is not None, "new": new,
            "groups": " ".join(new[i:i + 4] for i in range(0, len(new), 4)) if new else "",
            "uri": totp.uri(new) if new else "",
            "qr": Markup(segno.make(totp.uri(new), error="m").svg_inline(scale=4)) if new else "",
            "error": request.session.pop("totp_error", None),
            "codes": request.session.pop(RECOVERY_SHOWN_KEY, None), "left": recovery.left(session)}


def _show_codes(request: Request, session: Session) -> None:
    """Make ten recovery codes, keep their digests, and show the codes on the next settings page once (#1316)."""
    codes = recovery.new_codes()
    recovery.save(session, codes)
    request.session[RECOVERY_SHOWN_KEY] = [recovery.shown(c) for c in codes]


def _new_epoch(request: Request, session: Session) -> None:
    epoch = session_epoch(session) + 1
    session.merge(Setting(key=SESSION_EPOCH, value=str(epoch)))
    session.commit()
    request.session[EPOCH_KEY] = epoch


@router.post("/settings/totp/start", dependencies=[Depends(require_login), Depends(verify_csrf)])
def totp_start(request: Request) -> RedirectResponse:
    """Make a new secret and keep it only in the login session until a correct code (#1314)."""
    request.session[NEW_TOTP_KEY] = totp.new_secret()
    return RedirectResponse("/settings#totp", status_code=303)


@router.post("/settings/totp/on", dependencies=[Depends(require_login), Depends(verify_csrf)])
def totp_on(request: Request, code: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    """A correct code of the new secret saves it: the step is on, the other devices log in again (#1314)."""
    secret = request.session.get(NEW_TOTP_KEY)
    step = totp.check(secret, code, clock.time(), -1) if secret else None
    if step is None:
        request.session["totp_error"] = "Wrong code."
        return RedirectResponse("/settings#totp", status_code=303)
    session.merge(Setting(key=TOTP_SECRET, value=secret))
    session.merge(Setting(key=TOTP_STEP, value=str(step)))
    request.session.pop(NEW_TOTP_KEY, None)
    _show_codes(request, session)
    _new_epoch(request, session)
    request.session["flash"] = "The second login step is on. All other devices are logged out."
    return RedirectResponse("/settings#totp", status_code=303)


@router.post("/settings/totp/off", dependencies=[Depends(require_login), Depends(verify_csrf)])
def totp_off(request: Request, code: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    """A correct current code deletes the secret: the step is off, the other devices log in again (#1314)."""
    secret, last = session.get(Setting, TOTP_SECRET), session.get(Setting, TOTP_STEP)
    step = totp.check(secret.value, code, clock.time(), int(last.value) if last else -1) if secret else None
    if step is None:
        request.session["totp_error"] = "Wrong code."
        return RedirectResponse("/settings#totp", status_code=303)
    session.delete(secret)
    if last is not None:
        session.delete(last)
    recovery.delete(session)
    _new_epoch(request, session)
    request.session["flash"] = "The second login step is off. All other devices are logged out."
    return RedirectResponse("/settings#totp", status_code=303)


@router.post("/settings/totp/recovery", dependencies=[Depends(require_login), Depends(verify_csrf)])
def totp_recovery_new(request: Request, code: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
    """A correct current app code makes ten new recovery codes; the old ones stop working (#1316)."""
    secret, last = session.get(Setting, TOTP_SECRET), session.get(Setting, TOTP_STEP)
    step = totp.check(secret.value, code, clock.time(), int(last.value) if last else -1) if secret else None
    if step is None:
        request.session["totp_error"] = "Wrong code."
        return RedirectResponse("/settings#totp", status_code=303)
    session.merge(Setting(key=TOTP_STEP, value=str(step)))
    _show_codes(request, session)
    session.commit()
    return RedirectResponse("/settings#totp", status_code=303)


class PasskeyIn(BaseModel):
    name: str = ""
    credential: dict


@router.post("/settings/passkeys/options", dependencies=[Depends(require_login), Depends(verify_csrf)])
def passkey_options(request: Request, session: Session = Depends(get_session)) -> Response:
    """The options of navigator.credentials.create() for a new passkey (#1558)."""
    return Response(passkeys.registration_options(request, session), media_type="application/json")


@router.post("/settings/passkeys", dependencies=[Depends(require_login), Depends(verify_csrf)])
def passkey_add(request: Request, body: PasskeyIn, session: Session = Depends(get_session)) -> JSONResponse:
    """Check and store the new passkey; a wrong challenge or origin is a 400 with the reason (#1558)."""
    try:
        row = passkeys.register(request, session, body.name, body.credential)
    except passkeys.PasskeyError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    request.session["flash"] = f"The passkey “{row.name}” is added."
    return JSONResponse({"id": row.id})


@router.post("/settings/passkeys/{passkey_id}/delete", dependencies=[Depends(require_login), Depends(verify_csrf)])
def passkey_remove(request: Request, passkey_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    row = session.get(Passkey, passkey_id)
    if row is not None:
        session.delete(row)
        session.commit()
        request.session["flash"] = f"The passkey “{row.name}” is removed."
    return RedirectResponse("/settings#passkeys", status_code=303)


@router.post("/settings/sessions/end-others", dependencies=[Depends(require_login), Depends(verify_csrf)])
def end_other_sessions(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    """Make the session cookies of all other browsers invalid: +1 on the epoch (#1266)."""
    _new_epoch(request, session)
    request.session["flash"] = "All other devices are logged out."
    return RedirectResponse("/settings", status_code=303)


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
        "reminder_days": setting(session, REMINDER_DAYS_KEY, "0"),
        "reminder_before_days": setting(session, REMINDER_BEFORE_KEY, "14"), "max_reminder_days": MAX_REMINDER_DAYS,
        "travel_day_hours": setting(session, TRAVEL_DAY_HOURS_KEY, "0"), "max_travel_day_hours": MAX_TRAVEL_DAY_HOURS,
        "source_alert": setting(session, SOURCE_ALERT_KEY, "1"),
        "horizons": [(src, setting(session, sales_open.HORIZON_KEY.format(source=src))) for src in all_sources()],
        "smtp_ready": bool(get_settings().smtp_host),
        "vapid_public_key": get_settings().vapid_public_key if webpush_ready() else "",
        "push_count": session.scalar(select(func.count()).select_from(PushSubscription)),
        "messages": session.scalars(select(SentMessage).order_by(SentMessage.sent_at.desc(), SentMessage.id.desc())
                                    .limit(50)).all(),  # #1813
        "now": datetime.now(timezone.utc), "base_url": str(request.base_url).rstrip("/"),
        "flash": request.session.pop("flash", None)})


@router.post("/settings/messages/test", dependencies=[Depends(require_login), Depends(verify_csrf)])
def test_message(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    """Send one test message by the active channel, with no wait for a price drop (#1086)."""
    click = str(request.base_url).rstrip("/") + "/settings/messages"
    msgs = alert_messages(session, "Test message from travel-aggregator",
                          "The channel of travel-aggregator works.", click)
    if msgs:
        deliver(msgs, session=session)
        request.session["flash"] = f"Test message sent by {msgs[0].channel}"
    else:
        request.session["flash"] = "Select a channel first"
    return RedirectResponse("/settings/messages", status_code=303)


async def _travel_day_field(request: Request) -> str:
    """The raw field travel_day_hours (#1650): a blank value stays "" (422), a field that the form did not send is kept."""
    return str((await request.form()).get("travel_day_hours", REMINDER_NOT_SENT))


@router.post("/settings/messages",dependencies=[Depends(require_login), Depends(verify_csrf)])
def save_messages(notify_channel: str = Form("none"), ntfy_url: str = Form(""), notify_email: str = Form(""),
                  reminder_days: str = Form(REMINDER_NOT_SENT), reminder_before_days: str = Form(REMINDER_NOT_SENT),
                  source_alert: str = Form(REMINDER_NOT_SENT), travel_day_hours: str = Depends(_travel_day_field),
                  session: Session = Depends(get_session)) -> RedirectResponse:
    url = ntfy_url.strip()
    # #1117: a field that the form did not send is kept; a value that is not a whole number gives 422 and stores nothing.
    for label, value in (("the reminder age", reminder_days), ("the reminder before departure", reminder_before_days)):
        if value != REMINDER_NOT_SENT and not (value.strip().isascii() and value.strip().isdigit()
                                               and int(value.strip()) <= MAX_REMINDER_DAYS):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{label} must be a whole number from 0 to {MAX_REMINDER_DAYS} days")
    if travel_day_hours != REMINDER_NOT_SENT and not (travel_day_hours.strip().isascii()
                                                      and travel_day_hours.strip().isdigit()
                                                      and int(travel_day_hours.strip()) <= MAX_TRAVEL_DAY_HOURS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"the travel-day message must be a whole number from 0 to {MAX_TRAVEL_DAY_HOURS} hours")
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
    if reminder_days != REMINDER_NOT_SENT:
        session.merge(Setting(key=REMINDER_DAYS_KEY, value=str(int(reminder_days.strip()))))
    if reminder_before_days != REMINDER_NOT_SENT:
        session.merge(Setting(key=REMINDER_BEFORE_KEY, value=str(int(reminder_before_days.strip()))))
    if source_alert != REMINDER_NOT_SENT:  # #1174: the hidden field 0 comes before the checkbox 1
        session.merge(Setting(key=SOURCE_ALERT_KEY, value="1" if source_alert == "1" else "0"))
    if travel_day_hours != REMINDER_NOT_SENT:
        session.merge(Setting(key=TRAVEL_DAY_HOURS_KEY, value=str(int(travel_day_hours.strip()))))
    session.commit()
    return RedirectResponse("/settings/messages", status_code=303)


@router.post("/settings/sales-open", dependencies=[Depends(require_login), Depends(verify_csrf)])
async def save_sales_open(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    """The booking horizon in days per source (#2255). A blank field removes it; a bad value changes nothing."""
    form = await request.form()
    values = {src: str(form.get(f"horizon_{src}", "")).strip() for src in all_sources()
              if f"horizon_{src}" in form}
    for src, value in values.items():
        if value and not (value.isascii() and value.isdecimal()
                          and sales_open.MIN_DAYS <= int(value) <= sales_open.MAX_DAYS):
            request.session["flash"] = (f"The booking horizon of {src} must be a whole number from "
                                        f"{sales_open.MIN_DAYS} to {sales_open.MAX_DAYS} days. Nothing changed.")
            return RedirectResponse("/settings/messages", status_code=303)
    for src, value in values.items():
        key = sales_open.HORIZON_KEY.format(source=src)
        if value:
            session.merge(Setting(key=key, value=str(int(value))))
        elif (row := session.get(Setting, key)) is not None:
            session.delete(row)
    session.commit()
    request.session["flash"] = "Booking horizons saved"
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
    # a share from the phone opens the share path of the app (#2105, #2104)
    "share_target": {"action": "/share", "method": "GET", "enctype": "application/x-www-form-urlencoded",
                     "params": {"title": "title", "text": "text", "url": "url"}},
}


@router.get("/manifest.webmanifest", include_in_schema=False)
def web_app_manifest() -> Response:
    """The web app manifest (#797): the name, colours and icons of the app on a phone. No secret: no login."""
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


COMPARE_ERROR = "Select 2 to 4 offers of this trip."


def _span(minutes: int) -> str:
    return f"{minutes // 60} h" if minutes % 60 == 0 else f"{minutes // 60} h {minutes % 60:02d} min"


def tradeoff_lines(rows, shown, source, places, weights: Weights, stale_before, rates,
                   trip_id: int, base_qs: dict, counts=None, fees=None) -> dict:
    """The break-even line of each rendered row against the shown row with the lowest effective cost (#895).
    The best row and a row with no break-even get no line. Each line is (head, value, tail, link or None):
    the value is the link to this page with that hour value (#920)."""
    if not shown:
        return {}
    best = min(shown, key=lambda r: r[2].total)
    higher = dataclasses.replace(weights, hour_markup=weights.hour_markup + 1)
    def nxt(it):
        fares = [f for f in it.fares if not source or f.source == source]
        return row_cost(it, fares, places, higher, stale_before, rates, counts, fees)[1].total
    best_next, lines, yours = nxt(best[0]), {}, _amount(weights.hour_markup)
    price_lines = lines["price"] = {}
    for it, _, cost in rows:
        if it.id == best[0].id:
            continue
        at = best_at_price(best[2].total, cost.price, cost.total)  # the price at which this row is the best (#1965)
        if at is not None:
            price_lines[it.id] = _amount(at)
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
    lower, upper = best_range(best[2].total, best_next,
                              [(c.total, nxt(i)) for i, _, c in shown if i.id != best[0].id], weights.hour_markup)
    if lower is not None or upper is not None:
        def part(value, rounding):  # lower limit up, upper limit down: the best row stays best (#1936)
            rounded = value.to_integral_value(rounding=rounding)
            link = None
            if Decimal(0) <= rounded <= 100:
                link = f"/trips/{trip_id}?" + urlencode({**base_qs, "hour_markup": str(int(rounded))}, doseq=True)
            return (f"{_amount(value)}/h", link)
        segments = [("best ", None)]
        if lower is not None:
            segments += [("from ", None), part(lower, ROUND_CEILING)]
        if upper is not None:
            segments += [(" to " if lower is not None else "up to ", None), part(upper, ROUND_FLOOR)]
        segments.append((f" (yours: {yours}/h)", None))
        lines["best"] = (best[0].id, segments)
    return lines


def _parts_view(columns: list, best_n: int) -> list:
    """The part rows of the compare view (#2087): (label, [(amount, difference, is best) per column])."""
    costs = [cost for _, _, cost in columns]
    rows = []
    for row in part_rows(costs):
        cells = []
        for n, (cell, diff) in enumerate(zip(row.cells, row.diffs)):
            text = "no rate" if cell is None else _amount(cell)
            dtext = "" if diff is None or diff == 0 else ("+" if diff > 0 else "−") + _amount(abs(diff))
            cells.append((text, dtext, n == best_n and not costs[n].no_rate))
        rows.append((row.label, cells))
    return rows


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
    places = trip_places(session, trip)  # (#2109)
    stale_before = datetime.now(timezone.utc) - timedelta(hours=weights.stale_hours)
    rates = load_rates(session)
    counts = fare_travelers(session, found.values())  # the same price per traveler as the trip page (#767)
    fees = load_fees(session)  # the same booking fees as the trip page (#1143)
    for i in ids:
        fare, cost = row_cost(found[i], found[i].fares, places, weights, stale_before, rates, counts, fees)
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
    nexts = [row_cost(found[i], found[i].fares, places, higher, stale_before, rates, counts, fees)[1].total for i in ids]
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
    context["parts"] = _parts_view(context["columns"], best_n)  # the parts side by side (#2087)
    return templates.TemplateResponse(request, "compare.html", context)
