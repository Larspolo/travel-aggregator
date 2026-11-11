"""The log of the login attempts at the login page and the second step (#1353)."""

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import LoginEvent

LOGIN_LOG_KEEP = 200


def record(session: Session, request: Request, result: str) -> None:
    """Add one row and delete the rows older than the newest LOGIN_LOG_KEEP. The caller commits."""
    address = request.client.host if request.client else "unknown"
    agent = (request.headers.get("user-agent") or "")[:300]
    session.add(LoginEvent(at=datetime.now(timezone.utc), address=address[:64], user_agent=agent, result=result))
    session.flush()
    keep = select(LoginEvent.id).order_by(LoginEvent.id.desc()).limit(LOGIN_LOG_KEEP)
    session.execute(delete(LoginEvent).where(LoginEvent.id.not_in(keep)))


def recent(session: Session, n: int = 20) -> list[LoginEvent]:
    """The newest n rows, newest first."""
    return list(session.scalars(select(LoginEvent).order_by(LoginEvent.id.desc()).limit(n)))


# The order matters: Edge and Samsung Internet also send "Chrome/", and Chrome also sends "Safari/".
# An iPhone sends "Mac OS X" and Android sends "Linux", so those systems come first.
BROWSERS = (("Edg/", "Edge"), ("SamsungBrowser/", "Samsung Internet"), ("Firefox/", "Firefox"),
            ("Chrome/", "Chrome"), ("Safari/", "Safari"))
SYSTEMS = (("Windows NT", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
           ("Macintosh", "macOS"), ("Mac OS X", "macOS"), ("Linux", "Linux"))


def browser_name(text: str) -> str:
    """'<browser> on <system>' for a known User-Agent, else its first 40 characters (untrusted text)."""
    if not text:
        return "unknown browser"
    browser = next((name for part, name in BROWSERS if part in text), None)
    system = next((name for part, name in SYSTEMS if part in text), None)
    if browser and system:
        return f"{browser} on {system}"
    return text[:40]
