"""framework/tools/health.py counts only real tickets as given back: a deep run with no ticket reports `ticket #0`
(an epic check, a refill, a review) with the result `none`. That is deep work, not a lost ticket (lever 12): the
review of 2026-11-09 read "given back 6 (none 5)" and "#0 2", but only 5 tickets were lost."""
import health


def comment(*lines):
    return {"body": "\n".join(lines)}


LINES = [
    comment("Deep run, refill.", "Metrics: ticket #0 · size:- · none · 4 min · setup 0 min · lane deep"),
    comment("Deep run, epic check.", "Metrics: ticket #0 · size:- · none · 3 min · setup 0 min · lane deep"),
    comment("Released.", "Metrics: ticket #1317 · size:S · none · 0 min · setup 0 min",
            "Metrics: ticket #1315 · size:M · none · 1 min · setup 0 min"),
    comment("Blocked.", "Metrics: ticket #1299 · size:M · blocked · 4 min · setup 0 min"),
    comment("Again.", "Metrics: ticket #1299 · size:M · needs-human · 2 min · setup 0 min"),
    comment("Checked.", "Metrics: ticket #0 · size:- · checked · 1 min · setup 0 min"),
]


def test_ticket_zero_is_not_given_back():
    assert health.given_back(LINES) == {"none": 2, "blocked": 1, "needs-human": 1}


def test_ticket_zero_is_not_a_repeat():
    checks, repeats = health.back_causes(LINES)
    assert repeats == {1299: 2}
    assert checks == 0
