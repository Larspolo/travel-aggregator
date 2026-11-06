"""The score profiles (#229): a `Weights` to a JSON config and back, and the save of a named profile."""

import dataclasses
from datetime import time
from decimal import Decimal

from sqlalchemy import select
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
