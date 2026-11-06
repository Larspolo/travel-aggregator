"""An owner ticket that the agents make early waits with `blocked` for its agent work (owner, 2026-11-06).

"Waiting for you" shows only the owner tickets that the owner can do now, and the orphan check tells the runs to
remove `blocked` when all its "Depends on" tickets are closed.
"""
import datetime

import dashboard

NOW = datetime.datetime(2026, 11, 6, 12, 0, tzinfo=datetime.timezone.utc)


def issue(n, labels=(), body=""):
    return {"number": n, "title": f"Ticket {n}", "labels": [{"name": x} for x in labels], "body": body}


def waiting(issues):
    return dashboard.render("", issues, {}, [], [], [], NOW).split("### Waiting for you")[1].split("###")[0]


def test_waiting_shows_only_the_owner_tickets_of_now():
    issues = [issue(1, ["needs-human"]), issue(2, ["needs-human", "blocked"], "Depends on: #3"), issue(3, ["P3"])]
    wait = waiting(issues)
    assert "#1 Ticket 1" in wait and "#2 Ticket 2" not in wait
    assert "Later: 1 ticket " in wait


def test_an_owner_ticket_with_closed_depends_is_an_orphan():
    issues = [issue(1, ["needs-human", "blocked"], "Depends on: #9"),      # #9 is closed: the owner can do it now
              issue(2, ["needs-human", "blocked"], "Depends on: #3"), issue(3, ["P3"]),    # #3 is open
              issue(4, ["needs-human", "blocked"]),                         # no line: the owner sees it (old rule)
              issue(5, ["needs-human", "blocked", "muted"], "Depends on: #9")]
    got = dict(dashboard.orphans(issues))
    assert sorted(got) == [1]
    assert "remove `blocked`" in got[1]
