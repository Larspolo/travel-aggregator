"""The chart of the price against the door-to-door hours of the shown offers (#1858): an inline SVG."""

from decimal import Decimal

from app.money import money

PAD = 6  # room for the radius of a point at the edge


def _scale(value: float, low: float, high: float, size: float) -> float:
    return size / 2 if high == low else (value - low) / (high - low) * size


def pareto_chart(points: list[tuple[int, str, Decimal, int]], marked: set[int], width: float = 320,
                 height: float = 160, currency: str = "EUR") -> dict | None:
    """Give the chart of the (id, route, price, minutes) points: x is the hours, y is the price (low at the
    bottom). The ids in `marked` are filled and joined by a line. Fewer than 2 points: no chart."""
    if len(points) < 2:
        return None
    low_p, high_p = min(p[2] for p in points), max(p[2] for p in points)
    low_m, high_m = min(p[3] for p in points), max(p[3] for p in points)
    dots = []
    for id_, route, price, minutes in points:
        hours = f"{minutes // 60}h{minutes % 60:02d}"
        dots.append({"id": id_, "marked": id_ in marked,
                     "x": round(PAD + _scale(minutes, low_m, high_m, width - 2 * PAD), 1),
                     "y": round(PAD + height - 2 * PAD - _scale(float(price), float(low_p), float(high_p),
                                                               height - 2 * PAD), 1),
                     "title": f"{route}: {money(price, currency)}, {hours} door to door"})
    line = " ".join(f"{d['x']},{d['y']}" for d in sorted((d for d in dots if d["marked"]), key=lambda d: d["x"]))
    return {"width": width, "height": height, "dots": dots, "line": line, "currency": currency,
            "low_price": low_p, "high_price": high_p,
            "low_hours": f"{low_m // 60}h{low_m % 60:02d}", "high_hours": f"{high_m // 60}h{high_m % 60:02d}"}
