"""API tokens for the userscripts.

    python -m app.tokens create NAME    # prints the new token once; the database keeps only its hash
    python -m app.tokens list
    python -m app.tokens revoke ID
"""

import argparse
import secrets
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_token
from app.db import make_engine, make_sessionmaker
from app.models import ApiToken


def create(session: Session, name: str) -> str:
    """A new token (shown once) for NAME; its hash goes into api_tokens."""
    token = secrets.token_urlsafe(32)
    session.add(ApiToken(name=name, token_hash=hash_token(token)))
    session.commit()
    return token


def revoke(session: Session, token_id: int) -> bool:
    token = session.get(ApiToken, token_id)
    if token is None or token.revoked_at is not None:
        return False
    token.revoked_at = datetime.now(UTC)
    session.commit()
    return True


def main(argv: list[str] | None = None, session: Session | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.tokens", description="API tokens for the userscripts")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("create").add_argument("name")
    sub.add_parser("list")
    sub.add_parser("revoke").add_argument("id", type=int)
    a = ap.parse_args(argv)
    session = session or make_sessionmaker(make_engine())()
    with session:
        if a.command == "create":
            print(create(session, a.name))
            print("Keep this token: it shows only now.", file=sys.stderr)
        elif a.command == "list":
            for t in session.scalars(select(ApiToken).order_by(ApiToken.id)):
                state = f"revoked {t.revoked_at:%Y-%m-%d}" if t.revoked_at else "active"
                used = f"{t.last_used_at:%Y-%m-%d %H:%M}" if t.last_used_at else "never"
                print(f"{t.id}\t{t.name}\t{state}\tlast used {used}")
        elif not revoke(session, a.id):
            print(f"no active token {a.id}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
