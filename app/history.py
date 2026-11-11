"""The SVG coordinates of the price history chart (#241): one line per fare, one point per capture.

x goes from the first to the last capture time of all fares, y from the lowest to the highest price (the higher price
is the higher point, so the lower y). The prices stay `Decimal`; only the coordinates are floats."""

from decimal import Decimal
from typing import Any

from app.money import money

PAD = 6.0


def _scale(value: float, low: float, high: float, size: float) -> float:
    if high == low:
        return size / 2
    return PAD + (value - low) / (high - low) * (size - 2 * PAD)


def chart(fares: list[Any], width: float = 320, height: float = 100) -> dict:
    """{"width", "height", "lines": [{"name", "points": "x,y ...", "dots": [{"x", "y", "title"}]}], "low", "high"}."""
    rows = [p for f in fares for p in f.prices]
    if not rows:
        return {"width": width, "height": height, "lines": [], "low": None, "high": None}
    times = [p.captured_at.timestamp() for p in rows]
    t0, t1 = min(times), max(times)
    low: Decimal = min(p.price for p in rows)
    high: Decimal = max(p.price for p in rows)
    lines = []
    for f in fares:
        dots = []
        for p in sorted(f.prices, key=lambda p: p.captured_at):
            x = _scale(p.captured_at.timestamp(), t0, t1, width)
            y = height - _scale(float(p.price), float(low), float(high), height)
            dots.append({"x": round(x, 1), "y": round(y, 1),
                         "title": f"{p.captured_at:%Y-%m-%d %H:%M}: {money(p.price, p.currency)}"})
        if dots:
            name = f"{f.source}: {f.fare_name or ''}"
            lines.append({"name": name, "points": " ".join(f"{d['x']},{d['y']}" for d in dots), "dots": dots})
    return {"width": width, "height": height, "lines": lines, "low": low, "high": high,
            "currency": rows[0].currency}


def trend_chart(points: list[tuple[Any, Decimal]], width: float = 320, height: float = 100,
                currency: str = "EUR", scores: list[tuple[Any, Decimal]] | None = None) -> dict:
    """The price trend of a trip (#851): one line of (date, price) points, as `chart()`. No points: no line.
    `scores`: a second line "Best effective cost per day" (#2141) on the same scale as the first."""
    if not points:
        return {"width": width, "height": height, "lines": [], "low": None, "high": None, "currency": currency}
    series = [("Cheapest price per day", points)] + ([("Best effective cost per day", scores)] if scores else [])
    every = [pt for _, pts in series for pt in pts]
    t0 = min(d.toordinal() for d, _ in every)
    t1 = max(d.toordinal() for d, _ in every)
    low = min(p for _, p in every)
    high = max(p for _, p in every)
    lines = []
    for name, pts in series:
        dots = [{"x": round(_scale(d.toordinal(), t0, t1, width), 1),
                 "y": round(height - _scale(float(p), float(low), float(high), height), 1),
                 "title": f"{d:%Y-%m-%d}: {money(p, currency)}"} for d, p in pts]
        lines.append({"name": name, "points": " ".join(f"{d['x']},{d['y']}" for d in dots), "dots": dots})
    return {"width": width, "height": height, "lines": lines, "low": low, "high": high, "currency": currency}
