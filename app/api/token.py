"""GET /api/token: the state of the API token of the request (#2047), for the userscript check.

A valid token gives its name and end date. A revoked or expired token, and an unknown or missing token, give 401
with the reason. The limit of the bad tokens per address (#412) applies first, as in `require_token()`.
The token itself is never logged."""

import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import bearer, hash_token, token_limiter
from app.db import get_session
from app.models import ApiToken

router = APIRouter()


def _unauthorized(address: str, detail: str) -> HTTPException:
    token_limiter.failure(address)
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


@router.get("/token")
def token_state(request: Request,
                credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                session: Session = Depends(get_session)) -> dict[str, str | None]:
    address = request.client.host if request.client else "unknown"
    wait = token_limiter.retry_after(address)
    if wait > 0:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many bad API tokens",
                            headers={"Retry-After": str(wait)})
    if credentials is None or not credentials.credentials:
        raise _unauthorized(address, "invalid or missing API token")
    digest = hash_token(credentials.credentials)
    token = session.scalar(select(ApiToken).where(ApiToken.token_hash == digest))
    if token is None or not hmac.compare_digest(token.token_hash, digest):
        raise _unauthorized(address, "invalid or missing API token")
    if token.revoked_at is not None:
        raise _unauthorized(address, "token revoked")
    if token.expires_at is not None and token.expires_at <= datetime.now(UTC):
        raise _unauthorized(address, "token expired")
    return {"name": token.name,
            "expires_at": token.expires_at.isoformat() if token.expires_at is not None else None}
