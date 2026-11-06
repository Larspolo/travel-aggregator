"""A muted ticket is no candidate, and "Waiting for you" hides it (owner, 2026-10-26)."""
import datetime

import dashboard


def issue(n, *names):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": x} for x in ("P2",) + names], body="")


def test_muted_is_no_candidate():
    issues = [issue(1), issue(2, "muted"), issue(3, "muted", "P1")]
    assert [i["number"] for i in dashboard.candidates(issues)] == [1]


def test_waiting_hides_muted():
    issues = [issue(1, "needs-human"), issue(2, "needs-human", "muted"), issue(3, "muted")]
    now = datetime.datetime(2026, 10, 26, 15, 0, tzinfo=datetime.timezone.utc)
    body = dashboard.render("", issues, {}, [], [], [], now)
    wait = body.split("### Waiting for you")[1].split("###")[0]
    assert "#1 Ticket 1" in wait and "#2 " not in wait
    assert "Muted: 2 tickets" in wait


def test_nothing_waits_when_all_are_muted():
    now = datetime.datetime(2026, 10, 26, 15, 0, tzinfo=datetime.timezone.utc)
    body = dashboard.render("", [issue(2, "needs-human", "muted")], {}, [], [], [], now)
    wait = body.split("### Waiting for you")[1].split("###")[0]
    assert "- nothing" in wait and "Muted: 1 ticket " in wait
