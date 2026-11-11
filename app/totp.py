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


USAGE = "usage: python3 -m app.totp off\n"
OFF_LINE = "The second login step is off."


def turn_off(session) -> bool:
    """Turn the second login step off without a code: delete its rows and end the other sessions.

    Returns False and changes nothing when the step is already off (no secret row).
    """
    from app.auth import SESSION_EPOCH, TOTP_SECRET, TOTP_STEP, session_epoch
    from app.models import Setting

    if session.get(Setting, TOTP_SECRET) is None:
        return False
    for key in (TOTP_SECRET, TOTP_STEP):
        row = session.get(Setting, key)
        if row is not None:
            session.delete(row)
    session.merge(Setting(key=SESSION_EPOCH, value=str(session_epoch(session) + 1)))
    session.commit()
    return True


def main(argv: list[str] | None = None) -> int:
    """`python3 -m app.totp off`: the emergency switch of the second login step (#1318). Exit 2 on a wrong argument."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    if args != ["off"]:
        sys.stderr.write(USAGE)
        return 2
    from app.db import make_engine, make_sessionmaker

    session = make_sessionmaker(make_engine())()
    with session:
        turn_off(session)
    print(OFF_LINE)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
