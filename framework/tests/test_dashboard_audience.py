""""Waiting for you" groups the needs-human tickets by `for-lars` and `for-jeroen` (#72)."""
import dashboard

AUDIENCE = {"for-lars": "Larspolo", "for-jeroen": "Jeroenvb3"}


def issue(n, *names):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": x} for x in ("needs-human",) + names], body="")


def test_groups_by_label():
    lines = dashboard.waiting([issue(1, "for-jeroen"), issue(2, "for-lars"), issue(3)], {}, AUDIENCE)
    text = "\n".join(lines)
    assert text.index("**For Larspolo**") < text.index("#2 ") < text.index("**For Jeroenvb3**") < text.index("#1 ")
    assert text.index("**Other**") < text.index("#3 ")


def test_no_audience_gives_flat_list():
    assert dashboard.waiting([issue(1)], {}, {})[0].startswith("- #1 ")
    assert dashboard.waiting([], {}, AUDIENCE) == ["- nothing"]
