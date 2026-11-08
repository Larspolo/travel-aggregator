"""The best offer of a trip for each profile (#1210): the first row of the ranked table of each profile. Stores nothing."""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Fare, Itinerary, ScoreProfile, Trip
from app.profiles import from_config, list_profiles
from app.ranking import Breakdown


@dataclass(frozen=True)
class ProfileBest:
    """One profile and its first itinerary; `itinerary`, `fare` and `breakdown` are None when it has no row."""
    profile: ScoreProfile
    itinerary: Itinerary | None
    fare: Fare | None
    breakdown: Breakdown | None


def best_by_profile(session: Session, trip: Trip) -> list[ProfileBest]:
    """The best offer of `trip` for each profile, in the order of `list_profiles()`. The ranking is the one of the
    trip page (`best_for_weights()`): the same costs and the same tie order as the ranked table."""
    from app.web.pages import best_for_weights  # the web module imports much: import it only when needed

    result = []
    for profile in list_profiles(session):
        row = best_for_weights(session, trip, from_config(profile.config_json))
        result.append(ProfileBest(profile, *(row or (None, None, None))))
    return result
