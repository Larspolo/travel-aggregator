"""The export of the settings of the instance as one JSON file (#1206, epic #1204).

The file has only the rows that change the score and the behavior. It never has secrets, addresses or state keys
(P5): the `Setting` keys are an allow list, so a new secret key never goes into the file by accident.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_login
from app.db import get_session
from app.models import AccessTime, CurrencyRate, ScoreProfile, Setting, SourceFee
from app.notify import REMINDER_BEFORE_KEY, REMINDER_DAYS_KEY, SOURCE_ALERT_KEY
from app.retention import RETENTION_KEY

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
    values = session.scalars(select(Setting).where(Setting.key.in_(SETTING_KEYS)).order_by(Setting.key))
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": (now or datetime.now(timezone.utc)).isoformat(),
        "profiles": [{"name": p.name, "is_default": p.is_default, "config": p.config_json} for p in profiles],
        "places": [{"place": a.place_text, "kind": a.kind, "minutes": a.minutes, "cost": str(a.cost)} for a in places],
        "rates": [{"code": r.code, "eur_per_unit": str(r.eur_per_unit)} for r in rates],
        "fees": [{"source": f.source, "amount": str(f.amount)} for f in fees],
        "settings": {s.key: s.value for s in values},
    }


@router.get("/settings/export.json", dependencies=[Depends(require_login)])
def export_settings(session: Session = Depends(get_session)) -> Response:
    now = datetime.now(timezone.utc)
    body = json.dumps(settings_export(session, now), ensure_ascii=False, indent=2)
    filename = f"travel-aggregator-settings-{now.date().isoformat()}.json"
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
