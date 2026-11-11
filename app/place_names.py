"""The place names of the owner, merged with the built-in city table (#2215, epic #2214)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlaceName
from app.tripmatch import ALIASES, fold


def aliases(session: Session) -> dict[str, tuple[str, ...]]:
    """The built-in ALIASES with the owner's place names added. A row whose city matches a key or a local name of
    a group adds its name to that group; another city makes a new group. ALIASES itself is not changed."""
    merged: dict[str, tuple[str, ...]] = dict(ALIASES)
    for row in session.scalars(select(PlaceName).order_by(PlaceName.id)):
        key = next((k for k, local in merged.items() if fold(row.city) in {fold(k), *map(fold, local)}), None)
        if key is None:
            merged[row.city] = (row.name,)
        elif fold(row.name) not in {fold(n) for n in merged[key]} | {fold(key)}:
            merged[key] = (*merged[key], row.name)
    return merged
