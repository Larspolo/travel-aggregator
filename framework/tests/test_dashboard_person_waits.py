"""A task of a person ("## For the owner") with no `needs-human` waits while its last comment is an agent comment
after the last removal of `needs-human`: no candidate, and an orphan line tells the run to ask again with
`needs-human` (#477 was a candidate of 3 runs). An agent comment before the removal is the answer of the capture
skill in the person's browser (#463): a candidate."""
import datetime

import dashboard

BODY = "## Goal\nA person checks the capture.\n\n## For the owner\nKind: outside\n1. Search on the site.\n"
T = "2026-11-07T12:20:00Z"
AGENT = {"body": "Update the script, then do step 2 again." + dashboard.FOOTER, "user": {"type": "User"},
         "created_at": T}
PERSON = {"body": "There is no menu.", "user": {"type": "User"}, "created_at": T}
BOT = {"body": "Closed by the Close workflow.", "user": {"type": "Bot"}, "created_at": T}
BEFORE, AFTER = dashboard.ts("2026-11-07T11:56:00Z"), dashboard.ts("2026-11-07T12:20:01Z")


def issue(n, body="", comments=0):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": "P2"}], body=body, comments=comments)


def test_a_person_task_waits_after_an_agent_comment():
    last = {1: (AGENT, BEFORE), 2: (PERSON, BEFORE), 3: (BOT, None), 6: (AGENT, AFTER), 7: (AGENT, None)}
    issues = [issue(1, BODY, 3), issue(2, BODY, 2), issue(3, BODY, 1), issue(4, BODY), issue(5, "## Goal\nCode.", 4),
              issue(6, BODY, 5), issue(7, BODY, 1)]
    read = []

    def comment(i):
        read.append(i["number"])
        return last[i["number"]]
    assert [i["number"] for i in dashboard.candidates(issues, last=comment)] == [2, 4, 5, 6]
    assert sorted(read) == [1, 2, 3, 6, 7]      # only the person tasks with a comment read GitHub
    assert [n for n, _ in dashboard.orphans(issues, last=comment)] == [1, 3, 7]


def test_needs_human_hides_the_person_task_from_the_orphans():
    i = issue(1, BODY, 3)
    i["labels"].append({"name": "needs-human"})
    assert dashboard.orphans([i], last=lambda _: (AGENT, None)) == []
    assert dashboard.candidates([i], last=lambda _: (AGENT, None)) == []


def test_last_comment_reads_the_last_removal_of_needs_human(monkeypatch):
    calls = []

    def api(path):
        calls.append(path)
        return [AGENT]
    events = [{"event": "unlabeled", "label": {"name": "needs-human"}, "created_at": "2026-11-07T11:19:15Z"},
              {"event": "unlabeled", "label": {"name": "in-progress"}, "created_at": "2026-11-07T12:00:00Z"},
              {"event": "unlabeled", "label": {"name": "needs-human"}, "created_at": "2026-11-07T11:56:04Z"}]
    monkeypatch.setattr(dashboard, "api", api)
    monkeypatch.setattr(dashboard, "pages", lambda path, limit=10: events)
    c, off = dashboard.last_comment(issue(477, BODY, 7))
    assert c is AGENT and calls == ["issues/477/comments?per_page=1&page=7"]
    assert off == datetime.datetime(2026, 11, 7, 11, 56, 4, tzinfo=datetime.timezone.utc)
    assert dashboard.last_comment(issue(1, BODY, 0)) == (None, None)
