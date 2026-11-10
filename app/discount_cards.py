"""The discount cards of the fares of a trip (#1751): the cards of the capture of the newest price of each fare
(`Capture.discounts`, #1750), and a warning when the current fares come from searches with different cards."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import departed
from app.models import Capture, FarePrice


def fare_cards(session: Session, itineraries) -> dict[int, list[str] | None]:
    """The fare id to the sorted card names of the capture of its newest price; None when the cards are not known."""
    ids = [f.id for it in itineraries for f in it.fares]
    if not ids:
        return {}
    rows = session.execute(select(FarePrice.fare_id, Capture.discounts)
                           .outerjoin(Capture, FarePrice.capture_id == Capture.id)
                           .where(FarePrice.fare_id.in_(ids))
                           .order_by(FarePrice.captured_at, FarePrice.id)).all()
    newest = dict(rows)  # the last row of each fare is its newest price
    return {k: sorted(str(c) for c in v) if isinstance(v, list) else None for k, v in newest.items()}


def cards_warning(itineraries, cards: dict, gone=(), now=None) -> str | None:
    """The warning when the fares that are not hidden, not departed and not gone use different card sets.
    A fare with no known cards does not count. E.g. "These fares use different discount cards: BahnCard 50, none"."""
    now = now or departed.clock()
    sets = {tuple(cards[f.id]) for it in itineraries if not it.hidden and not departed.is_departed(it, now)
            for f in it.fares if f.id not in gone and cards.get(f.id) is not None}
    if len(sets) < 2:
        return None
    names = [" + ".join(s) if s else "none" for s in sorted(sets, key=lambda s: (not s, s))]
    return "These fares use different discount cards: " + ", ".join(names)


def card_label(fare, cards: dict) -> str:
    """The card names to show after the fare name: empty when not known, none, or already in the fare name."""
    names = [c for c in cards.get(fare.id) or [] if c.lower() not in (fare.fare_name or "").lower()]
    return ", ".join(names)
