"""The CO₂ part of an offer (#1416): kg of CO₂ per hour of each leg, and a price per kg."""
from decimal import Decimal

from app.ranking import Weights

KG_HOUR_FIELDS = {
    "train": "co2_train_kg_h",
    "bus": "co2_bus_kg_h",
    "flight": "co2_flight_kg_h",
    "ferry": "co2_ferry_kg_h",
}


def co2_kg(itinerary, weights: Weights) -> Decimal:
    """The kg of CO₂ of one traveler: the hours of each leg times the kg per hour of its mode; another mode adds 0."""
    total = Decimal("0")
    for leg in itinerary.legs:
        field = KG_HOUR_FIELDS.get(leg.mode)
        if field is None:
            continue
        hours = Decimal((leg.arrive_at - leg.depart_at).total_seconds()) / Decimal(3600)
        total += hours * Decimal(getattr(weights, field))
    return total


def co2_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("CO₂ <kg> kg", amount) at the price per kg. A price of 0 or no CO₂ adds no part."""
    if weights.co2_price_kg == 0:
        return ()
    kg = co2_kg(itinerary, weights)
    if kg == 0:
        return ()
    return ((f"CO₂ {kg:.0f} kg", (kg * Decimal(weights.co2_price_kg)).quantize(Decimal("0.01"))),)
