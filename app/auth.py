"""The two kinds of auth: the owner login of the pages, and the API tokens of /api (`Authorization: Bearer <token>`).

OWNER_PASSWORD_HASH has the format pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>.
Make it with: python3 -m app.auth 'PASSWORD'
"""

import hashlib
import hmac
import logging
import math
import os
import secrets
import sys
import time
from collections import defaultdict, deque
from collections.abc import Callable
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
CSRF_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

log = logging.getLogger(__name__)


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


class LoginLimiter:
    """Limits the failed logins in memory (one uvicorn process; a restart resets the counts).

    Per address: ADDRESS_MAX failures in WINDOW lock that address for LOCK seconds.
    All addresses together: GLOBAL_MAX failures in GLOBAL_WINDOW lock the login for LOCK seconds.
    """

    ADDRESS_MAX = 5
    WINDOW = 15 * 60
    GLOBAL_MAX = 20
    GLOBAL_WINDOW = 60 * 60
    LOCK = 15 * 60

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.reset()

    def reset(self) -> None:
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.all_failures: deque[float] = deque()
        self.locked_until: dict[str, float] = {}
        self.global_locked_until = 0.0

    def retry_after(self, address: str) -> int:
        """The seconds until the login is open for the address, 0 when it is open now."""
        now = self.clock()
        until = max(self.locked_until.get(address, 0.0), self.global_locked_until)
        return math.ceil(until - now) if until > now else 0

    def failure(self, address: str) -> None:
        now = self.clock()
        log.warning("failed login from %s", address)
        own = self.failures[address]
        own.append(now)
        while own and own[0] <= now - self.WINDOW:
            own.popleft()
        self.all_failures.append(now)
        while self.all_failures and self.all_failures[0] <= now - self.GLOBAL_WINDOW:
            self.all_failures.popleft()
        if len(own) >= self.ADDRESS_MAX:
            self.locked_until[address] = now + self.LOCK
            own.clear()
            log.warning("login locked for %s for %d minutes", address, self.LOCK // 60)
        if len(self.all_failures) >= self.GLOBAL_MAX:
            self.global_locked_until = now + self.LOCK
            self.all_failures.clear()
            log.warning("login locked for all addresses for %d minutes (last address %s)", self.LOCK // 60, address)

    def success(self, address: str) -> None:
        self.failures.pop(address, None)
        self.locked_until.pop(address, None)


login_limiter = LoginLimiter()


def require_login(request: Request) -> None:
    if not request.session.get(SESSION_KEY):
        raise LoginRequired()


def csrf_token(request: Request) -> str:
    """The CSRF token of the session. It makes a new random token when the session has none."""
    token = request.session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token


async def verify_csrf(request: Request) -> None:
    """A dependency of the state-changing web forms: 403 when the token is missing or wrong.

    It reads the form field csrf_token or the header X-CSRF-Token (htmx sends it from hx-headers).
    """
    expected = request.session.get(CSRF_KEY)
    sent = request.headers.get(CSRF_HEADER)
    if not sent:
        form = await request.form()
        value = form.get(CSRF_KEY)
        sent = value if isinstance(value, str) else None
    if not expected or not sent or not hmac.compare_digest(sent.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="CSRF token missing or wrong")


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
