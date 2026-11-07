"""Check that the offers of a capture match the places and the date of the trip (#555). The check only gives a
warning: the offers are stored in any case."""

import re
import unicodedata
from datetime import date

from app.models import Trip
from app.schemas import OfferIn

MIN_WORD = 3  # shorter words ("a", "NL") are too common to tell two places apart

# English name of a city -> its local names (and the IATA code of its airport, for the flight sites). A text that
# names one of them matches each other name of the group (#558). Names are matched as whole words, after _fold.
ALIASES: dict[str, tuple[str, ...]] = {
    "Amsterdam": ("AMS",),
    "Brussels": ("Bruxelles", "Brussel"),
    "Cologne": ("Köln", "Koln"),
    "Copenhagen": ("København", "Kobenhavn"),
    "Florence": ("Firenze",),
    "The Hague": ("Den Haag",),
    "Lisbon": ("Lisboa", "LIS"),
    "Milan": ("Milano",),
    "Munich": ("München", "Muenchen"),
    "Prague": ("Praha",),
    "Venice": ("Venezia",),
    "Vienna": ("Wien",),
    "Warsaw": ("Warszawa",),
    "Zurich": ("Zürich", "Zuerich", "ZRH"),
}


def _fold(text: str) -> str:
    """Casefold the text and strip the diacritics: "Zürich" becomes "zurich"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]+", _fold(text)) if len(w) >= MIN_WORD}


def _phrase(text: str) -> str:
    """The folded words of the text, joined by one space: "Den  Haag" becomes "den haag"."""
    return " ".join(re.findall(r"[^\W_]+", _fold(text)))


def _groups(text: str) -> set[str]:
    """The English names of the ALIASES groups that the text names (as a whole word or phrase)."""
    padded = f" {_phrase(text)} "
    return {english for english, local in ALIASES.items()
            if any(f" {_phrase(name)} " in padded for name in (english, *local))}


def _place_matches(trip_text: str | None, name: str, code: str | None) -> bool:
    if not trip_text or not trip_text.strip():
        return True
    if code and _fold(trip_text.strip()) == _fold(code.strip()):
        return True
    if _words(trip_text) & _words(name):
        return True
    return bool(_groups(trip_text) & _groups(name))


def _date_matches(trip: Trip, day: date) -> bool:
    if trip.date_from is None:
        return True
    return trip.date_from <= day <= (trip.date_to or trip.date_from)


def mismatch(trip: Trip, offers: list[OfferIn]) -> str | None:
    """None when at least one offer matches the trip; else "places" (no offer goes from the origin to the
    destination) or "date" (the offers that match the places depart on another day)."""
    if not offers:
        return None
    by_place = [o for o in offers if _place_matches(trip.origin_text, o.legs[0].from_name, o.legs[0].from_code)
                and _place_matches(trip.destination_text, o.legs[-1].to_name, o.legs[-1].to_code)]
    if not by_place:
        return "places"
    if any(_date_matches(trip, o.legs[0].depart_at.date()) for o in by_place):
        return None
    return "date"


def suggest_trip(offers: list[OfferIn]) -> dict | None:
    """The trip that the offers suggest when no trip matches (#720): from the first leg of the first offer to its
    last leg, on the earliest departure day of the offers. The keys are those of TripIn (app/api/trips.py), so
    that the panel can POST the suggestion unchanged. None without offers."""
    if not offers:
        return None
    origin, destination = offers[0].legs[0].from_name, offers[0].legs[-1].to_name
    day = min(o.legs[0].depart_at.date() for o in offers)
    title = f"{origin} → {destination}"[:200]  # the title of TripIn has a limit of 200 characters
    return {"title": title, "origin_text": origin, "destination_text": destination, "date_from": day.isoformat()}


def best_trip(trips: list[Trip], offers: list[OfferIn], selected: Trip) -> Trip:
    """The trip for the offers of an `auto_trip` capture (#719): the selected trip when it matches; else the one
    trip with the status "planning" that matches (of 2 or more: the shortest date range, then the newest); else the
    selected trip (the caller gives the warning of #555)."""
    if mismatch(selected, offers) is None:
        return selected
    matches = [t for t in trips if t.status == "planning" and t.id != selected.id and mismatch(t, offers) is None]
    if not matches:
        return selected

    def days(t: Trip) -> int:
        if t.date_from is None:
            return 1 << 30  # no dates: the widest range
        return ((t.date_to or t.date_from) - t.date_from).days

    return min(matches, key=lambda t: (days(t), -t.id))
