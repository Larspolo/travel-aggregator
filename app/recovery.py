"""One-time recovery codes of the second login step, for a lost phone (#1316).

The codes are shown one time. The database keeps only their sha256 digests (the Setting `totp_recovery`).
"""

import hashlib
import hmac
import json
import secrets

from sqlalchemy.orm import Session

from app.auth import TOTP_RECOVERY
from app.models import Setting

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
COUNT = 10
LENGTH = 10


def new_codes() -> list[str]:
    """COUNT new codes of LENGTH characters, from the random source of the system."""
    return ["".join(secrets.choice(ALPHABET) for _ in range(LENGTH)) for _ in range(COUNT)]


def shown(code: str) -> str:
    """The form for the page and the user: xxxxx-xxxxx."""
    return f"{code[:LENGTH // 2]}-{code[LENGTH // 2:]}"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _normal(text: str) -> str:
    """The typed text without case, spaces and dashes."""
    return text.lower().replace(" ", "").replace("-", "")


def digests(session: Session) -> list[str]:
    row = session.get(Setting, TOTP_RECOVERY)
    return json.loads(row.value) if row else []


def left(session: Session) -> int:
    return len(digests(session))


def save(session: Session, codes: list[str]) -> None:
    """Replace all recovery codes by these. The caller commits."""
    session.merge(Setting(key=TOTP_RECOVERY, value=json.dumps([_digest(c) for c in codes])))


def delete(session: Session) -> None:
    row = session.get(Setting, TOTP_RECOVERY)
    if row is not None:
        session.delete(row)


def use(session: Session, given: str) -> bool:
    """True when `given` is an unused recovery code. Its digest is removed: the code works one time. The caller commits."""
    current = digests(session)
    wanted = _digest(_normal(given))
    match = None
    for d in current:  # no early exit: the time does not show the position of the code
        if hmac.compare_digest(d, wanted):
            match = d
    if match is None:
        return False
    current.remove(match)
    session.merge(Setting(key=TOTP_RECOVERY, value=json.dumps(current)))
    return True
