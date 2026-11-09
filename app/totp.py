"""One-time codes of an authenticator app (TOTP, RFC 6238 over HOTP, RFC 4226). Standard library only."""

import base64
import hashlib
import hmac
import secrets
import struct

STEP = 30
DIGITS = 6


def _key(secret: str) -> bytes:
    text = secret.strip().upper().replace(" ", "")
    text += "=" * (-len(text) % 8)
    return base64.b32decode(text)


def _hotp(key: bytes, step: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def new_secret() -> str:
    """A new secret: 20 random bytes as base32, without padding (32 characters)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def code(secret: str, now: float) -> str:
    """The 6-digit code of the 30-second step that contains `now` (Unix seconds)."""
    return _hotp(_key(secret), int(now) // STEP)


def check(secret: str, given: str, now: float, last_step: int) -> int | None:
    """The step of `given` when it is valid for the steps around `now` and later than `last_step`, else None."""
    text = given.replace(" ", "")
    if len(text) != DIGITS or not (text.isascii() and text.isdigit()):
        return None
    key = _key(secret)
    current = int(now) // STEP
    for step in (current - 1, current, current + 1):
        if step <= last_step:
            continue
        if hmac.compare_digest(_hotp(key, step), text):
            return step
    return None


def uri(secret: str) -> str:
    """The otpauth:// address that an authenticator app reads from a QR code."""
    return (
        f"otpauth://totp/travel-aggregator:owner?secret={secret}"
        "&issuer=travel-aggregator&algorithm=SHA1&digits=6&period=30"
    )
