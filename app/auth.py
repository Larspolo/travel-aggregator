"""The owner login: the password hash check and the login dependency of the pages.

OWNER_PASSWORD_HASH has the format pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>.
Make it with: python3 -m app.auth 'PASSWORD'
"""

import hashlib
import hmac
import os
import secrets
import sys

from fastapi import HTTPException, Request

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
SESSION_KEY = "owner"
CSRF_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


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


if __name__ == "__main__":
    print(make_password_hash(sys.argv[1] if len(sys.argv) > 1 else os.environ["OWNER_PASSWORD"]))
