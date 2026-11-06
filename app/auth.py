"""The two kinds of auth: the owner login of the pages, and the API tokens of /api (`Authorization: Bearer <token>`).

OWNER_PASSWORD_HASH has the format pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>.
Make it with: python3 -m app.auth 'PASSWORD'
"""

import hashlib
import hmac
import os
import secrets
import sys
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ApiToken

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
SESSION_KEY = "owner"


class LoginRequired(HTTPException):
    """A page needs a login: the app answers with a redirect to /login."""

    def __init__(self) -> None:
        super().__init__(status_code=303, headers={"Location": "/login"})


def make_password_hash(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored_hash: str) -> bool:
    """True when the password matches the stored hash. A bad or empty hash never matches."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$")
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except ValueError:
        return False


def require_login(request: Request) -> None:
    if not request.session.get(SESSION_KEY):
        raise LoginRequired()


# The API tokens: the database holds only the SHA-256 hash (P5).
bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                  session: Session = Depends(get_session)) -> ApiToken:
    """The valid, not revoked token of the request, else 401. Never log the token."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API token",
                                 headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or not credentials.credentials:
        raise unauthorized
    digest = hash_token(credentials.credentials)
    token = session.scalar(select(ApiToken).where(ApiToken.token_hash == digest, ApiToken.revoked_at.is_(None)))
    if token is None or not hmac.compare_digest(token.token_hash, digest):
        raise unauthorized
    token.last_used_at = datetime.now(UTC)
    session.commit()
    return token


if __name__ == "__main__":
    print(make_password_hash(sys.argv[1] if len(sys.argv) > 1 else os.environ["OWNER_PASSWORD"]))
