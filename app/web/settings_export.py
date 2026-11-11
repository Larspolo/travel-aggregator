"""The export of the settings of the instance as one JSON file (#1206, epic #1204), and its import (#1207).

The file has only the rows that change the score and the behavior. It never has secrets, addresses or state keys
(P5): the `Setting` keys are an allow list, so a new secret key never goes into the file by accident.
"""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import AccessTime, CurrencyRate, RailPass, ScoreProfile, Setting, SourceFee, TravelBudget
from app.notify import MAX_REMINDER_DAYS, REMINDER_BEFORE_KEY, REMINDER_DAYS_KEY, SOURCE_ALERT_KEY
from app.profiles import to_config
from app.retention import MAX_RETENTION_DAYS, RETENTION_KEY
from app.schemas import MAX_BODY_BYTES
from app.web.pages import form_weights, templates
from app.web.passes import _cost, _day

router = APIRouter()

FORMAT = "travel-aggregator-settings"
VERSION = 1
SETTING_KEYS = (RETENTION_KEY, REMINDER_DAYS_KEY, REMINDER_BEFORE_KEY, SOURCE_ALERT_KEY)


def settings_export(session: Session, now: datetime | None = None) -> dict:
    """The settings as a dict. Money and rates are strings with the exact Decimal value."""
    profiles = session.scalars(select(ScoreProfile).order_by(ScoreProfile.name))
    places = session.scalars(select(AccessTime).order_by(AccessTime.place_text, AccessTime.kind, AccessTime.id))
    rates = session.scalars(select(CurrencyRate).order_by(CurrencyRate.code))
    fees = session.scalars(select(SourceFee).order_by(SourceFee.source))
    passes = session.scalars(select(RailPass).order_by(RailPass.first_day, RailPass.name))
    budgets = session.scalars(select(TravelBudget).order_by(TravelBudget.year))
    values = session.scalars(select(Setting).where(Setting.key.in_(SETTING_KEYS)).order_by(Setting.key))
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": (now or datetime.now(timezone.utc)).isoformat(),
        "profiles": [{"name": p.name, "is_default": p.is_default, "config": p.config_json} for p in profiles],
        "places": [{"place": a.place_text, "kind": a.kind, "minutes": a.minutes, "cost": str(a.cost)} for a in places],
        "rates": [{"code": r.code, "eur_per_unit": str(r.eur_per_unit)} for r in rates],
        "fees": [{"source": f.source, "amount": str(f.amount)} for f in fees],
        "passes": [{"name": p.name, "first_day": p.first_day.isoformat(), "last_day": p.last_day.isoformat(),
                    "day_cost": str(p.day_cost), "carriers": p.carriers} for p in passes],
        "travel_budgets": [{"year": b.year, "amount": str(b.amount)} for b in budgets],
        "settings": {s.key: s.value for s in values},
    }


@router.get("/settings/export.json", dependencies=[Depends(require_login)])
def export_settings(session: Session = Depends(get_session)) -> Response:
    now = datetime.now(timezone.utc)
    body = json.dumps(settings_export(session, now), ensure_ascii=False, indent=2)
    filename = f"travel-aggregator-settings-{now.date().isoformat()}.json"
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# The values of each settings key: a check that gives an error text or None (#1207).
def _whole(high: int):
    return lambda v: None if isinstance(v, str) and v.isascii() and v.isdigit() and int(v) <= high \
        else f"must be a whole number from 0 to {high}"


SETTING_CHECKS = {RETENTION_KEY: _whole(MAX_RETENTION_DAYS), REMINDER_DAYS_KEY: _whole(MAX_REMINDER_DAYS),
                  REMINDER_BEFORE_KEY: _whole(MAX_REMINDER_DAYS),
                  SOURCE_ALERT_KEY: lambda v: None if v in ("0", "1") else "must be 0 or 1"}
CODE = re.compile(r"^[A-Z]{3}$")


def _decimal(value, low: Decimal, strict: bool, high: Decimal = Decimal("100000000"), places: int = 6):
    """A `Decimal` from a string or an int, or None when it is not a valid value."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not d.is_finite() or d >= high or d.as_tuple().exponent < -places or (d <= low if strict else d < low):
        return None
    return d


def _text(value, high: int) -> str | None:
    return value.strip() if isinstance(value, str) and 1 <= len(value.strip()) <= high else None


def check_file(data) -> tuple[dict, list[str]]:
    """The checked rows of a settings file and the errors. With an error, the import changes no row."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return {}, [f"The file is not a settings export (format {FORMAT!r})."]
    if data.get("version") != VERSION:
        return {}, [f"The version must be {VERSION}."]
    errors = []
    out = {"profiles": [], "places": [], "rates": [], "fees": [], "passes": [], "travel_budgets": [], "settings": {}}
    lists = {}
    for key in ("profiles", "places", "rates", "fees", "passes", "travel_budgets"):
        lists[key] = data.get(key, [])
        if not isinstance(lists[key], list) or not all(isinstance(x, dict) for x in lists[key]):
            errors.append(f"{key} must be a list of objects.")
            lists[key] = []
    for i, p in enumerate(lists["profiles"], 1):
        name, config = _text(p.get("name"), 100), p.get("config")
        if name is None or not isinstance(p.get("is_default", False), bool) or not isinstance(config, dict):
            errors.append(f"Profile {i}: it needs a name of 1 to 100 characters and a config object.")
            continue
        form = {k: "" if v is None else str(v) for k, v in config.items()}
        weights, error = form_weights(form)
        if error:
            errors.append(f"Profile {name}: {error}")
            continue
        out["profiles"].append((name, bool(p.get("is_default", False)), to_config(weights)))
    if sum(1 for p in out["profiles"] if p[1]) > 1:
        errors.append("At most one profile can be the default.")
    for i, a in enumerate(lists["places"], 1):
        place, kind, cost = _text(a.get("place"), 200), a.get("kind"), _decimal(a.get("cost"), Decimal(0), False,
                                                                                 places=2)
        minutes = a.get("minutes")
        if (place is None or kind not in ("access", "egress") or cost is None or isinstance(minutes, bool)
                or not isinstance(minutes, int) or not 0 <= minutes <= 1440):
            errors.append(f"Place {i}: it needs a place, a kind access or egress, minutes 0 to 1440 and a cost of "
                          "at least 0.")
            continue
        out["places"].append((place, kind, minutes, cost))
    for i, r in enumerate(lists["rates"], 1):
        code, rate = r.get("code"), _decimal(r.get("eur_per_unit"), Decimal(0), True)
        if not isinstance(code, str) or not CODE.match(code) or code == "EUR" or rate is None:
            errors.append(f"Rate {i}: it needs a code of 3 capital letters (not EUR) and a rate more than 0.")
            continue
        out["rates"].append((code, rate))
    for i, f in enumerate(lists["fees"], 1):
        source, amount = _text(f.get("source"), 50), _decimal(f.get("amount"), Decimal(0), False, places=2)
        if source is None or amount is None:
            errors.append(f"Fee {i}: it needs a source and an amount of at least 0.")
            continue
        out["fees"].append((source, amount))
    for i, p in enumerate(lists["passes"], 1):
        name, carriers = _text(p.get("name"), 100), p.get("carriers", "")
        first = _day(p["first_day"]) if isinstance(p.get("first_day"), str) else None
        last = _day(p["last_day"]) if isinstance(p.get("last_day"), str) else None
        cost = _cost(p["day_cost"]) if isinstance(p.get("day_cost"), str) else None
        if (name is None or first is None or last is None or last < first or cost is None
                or not isinstance(carriers, str) or len(carriers) > 300):
            errors.append(f"Pass {i}: it needs a name of 1 to 100 characters, two ISO dates with the last day on or "
                          "after the first day, a cost per day from 0 to 1000 with at most 2 decimals and carriers "
                          "of at most 300 characters.")
            continue
        out["passes"].append((name, first, last, cost, carriers.strip()))
    for i, b in enumerate(lists["travel_budgets"], 1):
        year, amount = b.get("year"), _decimal(b.get("amount"), Decimal(0), False, Decimal("1000000"), places=2)
        if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100 or amount is None:
            errors.append(f"Travel budget {i}: it needs a year from 2000 to 2100 and an amount from 0 to 1000000 "
                          "with at most 2 decimals.")
            continue
        out["travel_budgets"].append((year, amount))
    if len({y for y, _ in out["travel_budgets"]}) != len(out["travel_budgets"]):
        errors.append("travel_budgets has the same year two times.")
    values = data.get("settings", {})
    if not isinstance(values, dict):
        errors.append("settings must be an object.")
        values = {}
    for key, value in values.items():
        if key not in SETTING_CHECKS:
            errors.append(f"The settings key {key!r} is not known.")
        elif (error := SETTING_CHECKS[key](value)) is not None:
            errors.append(f"The setting {key} {error}.")
        else:
            out["settings"][key] = str(int(value))
    for key in ("profiles", "rates", "fees", "passes"):
        names = [x[0] for x in out[key]]
        if len(names) != len(set(names)):
            errors.append(f"{key} has the same name two times.")
    return out, errors


def apply_file(session: Session, rows: dict) -> str:
    """Change the rows of the checked file (the file wins); the caller commits. Gives the counts text."""
    now = datetime.now(timezone.utc)
    if any(p[1] for p in rows["profiles"]):
        session.execute(update(ScoreProfile).values(is_default=False))
        session.flush()
    for name, is_default, config in rows["profiles"]:
        profile = session.scalars(select(ScoreProfile).where(ScoreProfile.name == name)).first()
        if profile is None:
            profile = ScoreProfile(name=name, config_json=config, is_default=is_default)
            session.add(profile)
        profile.config_json = config
        if is_default:
            profile.is_default = True
    for place, kind, minutes, cost in rows["places"]:
        row = session.scalars(select(AccessTime).where(AccessTime.place_text == place, AccessTime.kind == kind)
                              .order_by(AccessTime.id)).first()
        if row is None:
            session.add(AccessTime(place_text=place, kind=kind, minutes=minutes, cost=cost))
        else:
            row.minutes, row.cost = minutes, cost
    for code, rate in rows["rates"]:
        row = session.get(CurrencyRate, code)
        if row is None:
            session.add(CurrencyRate(code=code, eur_per_unit=rate, updated_at=now))
        elif row.eur_per_unit != rate:
            row.eur_per_unit, row.updated_at = rate, now
    for source, amount in rows["fees"]:
        row = session.get(SourceFee, source)
        if row is None:
            session.add(SourceFee(source=source, amount=amount, updated_at=now))
        elif row.amount != amount:
            row.amount, row.updated_at = amount, now
    for name, first, last, cost, carriers in rows["passes"]:
        row = session.scalars(select(RailPass).where(RailPass.name == name)).first()
        if row is None:
            row = RailPass(name=name)
            session.add(row)
        row.first_day, row.last_day, row.day_cost, row.carriers = first, last, cost, carriers
        row.updated_at = now
    for year, amount in rows["travel_budgets"]:
        row = session.get(TravelBudget, year)
        if row is None:
            session.add(TravelBudget(year=year, amount=amount, updated_at=now))
        elif row.amount != amount:
            row.amount, row.updated_at = amount, now
    for key, value in rows["settings"].items():
        session.merge(Setting(key=key, value=value))

    def n(count: int, one: str, many: str) -> str:
        return f"{count} {one if count == 1 else many}"
    return (f"{n(len(rows['profiles']), 'profile', 'profiles')}, {n(len(rows['places']), 'place', 'places')}, "
            f"{n(len(rows['rates']), 'rate', 'rates')}, {n(len(rows['fees']), 'fee', 'fees')} and "
            f"{n(len(rows['settings']), 'setting', 'settings')} imported")


def _page(request: Request, errors: list[str] | None = None, done: str | None = None,
          code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings_import.html", {"errors": errors or [], "done": done},
                                      status_code=code)


@router.get("/settings/import", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def import_form(request: Request) -> HTMLResponse:
    return _page(request)


@router.post("/settings/import", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def import_file(request: Request, file: UploadFile | None = File(None),
                      session: Session = Depends(get_session)) -> HTMLResponse:
    raw = await file.read(MAX_BODY_BYTES + 1) if file is not None else b""
    if not raw:
        return _page(request, ["Select a settings file."], code=400)
    if len(raw) > MAX_BODY_BYTES:
        return _page(request, [f"The file is larger than {MAX_BODY_BYTES} bytes."], code=400)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return _page(request, ["The file is not JSON."], code=400)
    rows, errors = check_file(data)
    if errors:
        return _page(request, errors, code=400)
    try:
        done = apply_file(session, rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _page(request, done=done)
