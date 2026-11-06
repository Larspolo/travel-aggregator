"""The score profiles (#229): a `Weights` to a JSON config and back, and the save of a named profile."""

import dataclasses
from datetime import time
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ScoreProfile
from app.ranking import Weights


def to_config(weights: Weights) -> dict:
    """A `Decimal` as a string, a `time` as "HH:MM"; `None` stays `None`."""
    out = {}
    for f in dataclasses.fields(Weights):
        v = getattr(weights, f.name)
        if isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, time):
            v = v.strftime("%H:%M")
        out[f.name] = v
    return out


def from_config(config: dict) -> Weights:
    """A missing key takes the `Weights` default; an unknown key is ignored (an old profile loads after a new weight)."""
    values = {}
    for f in dataclasses.fields(Weights):
        if f.name not in config:
            continue
        v, default = config[f.name], f.default
        if v is None:
            values[f.name] = None
        elif isinstance(default, time):
            values[f.name] = time.fromisoformat(v)
        elif isinstance(default, int) and not isinstance(default, bool):
            values[f.name] = int(v)
        else:  # a Decimal, also the optional night_hour_markup (default None)
            values[f.name] = Decimal(str(v))
    return Weights(**values)


def save(session: Session, name: str, weights: Weights) -> ScoreProfile:
    """Store the weights as the profile `name`; a name that exists already gets the new config."""
    profile = session.scalars(select(ScoreProfile).where(ScoreProfile.name == name)).first()
    if profile is None:
        profile = ScoreProfile(name=name, config_json={})
        session.add(profile)
    profile.config_json = to_config(weights)
    session.commit()
    return profile


def list_profiles(session: Session) -> list[ScoreProfile]:
    """All profiles in the order of their creation (#233)."""
    return list(session.scalars(select(ScoreProfile).order_by(ScoreProfile.id)).all())


def set_default(session: Session, profile_id: int) -> bool:
    """Make `profile_id` the only default, in one transaction (#233). False when the profile does not exist."""
    profile = session.get(ScoreProfile, profile_id)
    if profile is None:
        return False
    session.execute(update(ScoreProfile).where(ScoreProfile.is_default).values(is_default=False))
    profile.is_default = True
    session.commit()
    return True


def rename(session: Session, profile_id: int, name: str) -> bool:
    """Give the profile a new name (#233). False when another profile has the name; nothing changes then."""
    taken = session.scalars(select(ScoreProfile.id).where(ScoreProfile.name == name,
                                                          ScoreProfile.id != profile_id)).first()
    if taken is not None:
        return False
    profile = session.get(ScoreProfile, profile_id)
    profile.name = name
    try:
        session.commit()
    except IntegrityError:  # a name that another request stored in the meantime
        session.rollback()
        return False
    return True


def delete(session: Session, profile_id: int) -> bool:
    """Remove the profile (#233). False when it does not exist."""
    profile = session.get(ScoreProfile, profile_id)
    if profile is None:
        return False
    session.delete(profile)
    session.commit()
    return True
