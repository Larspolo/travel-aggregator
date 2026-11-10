"""The metrics of the app for Prometheus (#1892): GET /metrics with the metrics token. The database holds only the hash
of the token (P5)."""

import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import bearer, hash_token, require_login, verify_csrf
from app.db import get_session
from app.models import Itinerary, Setting, Trip

KEY = "metrics_token_hash"
MEDIA_TYPE = "text/plain; version=0.0.4"

router = APIRouter()


def new_metrics_token(session: Session) -> str:
    """Give a new metrics token. It replaces the last token: the old token stops."""
    token = secrets.token_urlsafe(32)
    setting = session.get(Setting, KEY)
    if setting is None:
        session.add(Setting(key=KEY, value=hash_token(token)))
    else:
        setting.value = hash_token(token)
    return token


def revoke_metrics_token(session: Session) -> None:
    setting = session.get(Setting, KEY)
    if setting is not None:
        session.delete(setting)


def metrics_token_ok(session: Session, token: str) -> bool:
    """True if the token is the metrics token. The hash is compared in constant time."""
    setting = session.get(Setting, KEY)
    if setting is None or not setting.value:
        return False
    return hmac.compare_digest(setting.value.encode(), hash_token(token).encode())


def metrics_text(session: Session) -> str:
    """The body in the text format of Prometheus."""
    values = [
        ("travel_trips", "The count of trips, also the archived trips.", session.scalar(select(func.count(Trip.id)))),
        ("travel_offers", "The count of itineraries.", session.scalar(select(func.count(Itinerary.id)))),
    ]
    lines = []
    for name, help_text, value in values:
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]
    return "\n".join(lines) + "\n"


@router.get("/metrics")
def metrics(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
            session: Session = Depends(get_session)) -> PlainTextResponse:
    if credentials is None or not metrics_token_ok(session, credentials.credentials):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing metrics token",
                            headers={"WWW-Authenticate": "Bearer"})
    return PlainTextResponse(metrics_text(session), media_type=MEDIA_TYPE)


@router.post("/settings/metrics-token", dependencies=[Depends(require_login), Depends(verify_csrf)])
def make_token(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    token = new_metrics_token(session)
    session.commit()
    request.session["metrics_token"] = token  # the settings page shows it once
    return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/metrics-token/revoke", dependencies=[Depends(require_login), Depends(verify_csrf)])
def stop_token(session: Session = Depends(get_session)) -> RedirectResponse:
    revoke_metrics_token(session)
    session.commit()
    return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)
