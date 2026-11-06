"""A ticket with "Start after: N PRs after #M" waits for N merged PRs after PR #M (#2039), and dashboard.merges()
counts the squash merges of the default branch."""
import datetime

import dashboard

UTC = datetime.timezone.utc


def issue(n, body=""):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": "P2"}], body=body)


def test_start_after_a_count_of_merged_prs(monkeypatch):
    # a merge just now: the idle limit of waits() does not end the wait. With no patch, the test reads the live merges
    # of the repository, and a new repository with no merge fails it.
    monkeypatch.setattr(dashboard, "merges", lambda **k: [(datetime.datetime(2026, 10, 28, tzinfo=UTC), 1)])
    issues = [issue(1, "## Goal\nStart after: 100 PRs after #2026\n"), issue(2), issue(3, "Start after: 1 PR after #7"),
              issue(4, "Text: Start after: 5 PRs after #9 in a sentence."), issue(5, "Start after: 2026-10-27 05:15 UTC")]
    now = datetime.datetime(2026, 10, 28, tzinfo=UTC)
    pick = lambda counts: [i["number"] for i in dashboard.candidates(issues, now=now, after=counts.get)]
    assert pick({}) == [2, 4, 5]                                     # #2026 and #7 are not merged yet
    assert pick({2026: 99, 7: 0}) == [2, 4, 5]
    assert pick({2026: 100, 7: 1}) == [1, 2, 3, 4, 5]
    assert dashboard.start_after_prs(issues[0]) == (100, 2026) and dashboard.start_after_prs(issues[4]) is None
    assert dashboard.start_after(issues[0]) is None                  # the time form does not read the PR form


def test_merges_counts_the_squash_merges(monkeypatch):
    def commit(subject, t):
        return {"commit": {"message": subject + "\n\nbody", "committer": {"date": t}}}
    pages = {1: [commit("Add the login page (#1821)", "2026-10-27T20:50:00Z"),
                 commit("Update the generated files: coverage report", "2026-10-27T20:40:00Z"),
                 commit("Fix #12 in the text, not at the end", "2026-10-27T20:35:00Z"),
                 commit("Move the tables to data files (#1917)", "2026-10-27T20:30:00Z")]}
    calls = []

    def api(path):
        calls.append(path)
        return pages.get(int(path.rsplit("page=", 1)[1].split("&")[0]), [])
    monkeypatch.setattr(dashboard, "api", api)
    t = lambda s: datetime.datetime.fromisoformat(s + "+00:00")
    assert dashboard.merges() == [(t("2026-10-27T20:50:00"), 1821), (t("2026-10-27T20:30:00"), 1917)]
    assert dashboard.merges(until=t("2026-10-27T20:45:00")) == [(t("2026-10-27T20:30:00"), 1917)]
    assert dashboard.merges(n=1) == [(t("2026-10-27T20:50:00"), 1821)]
    dashboard.merges(since=t("2026-10-27T20:00:00"))
    assert calls[-1].endswith("&since=2026-10-27T20:00:00Z") and f"sha={dashboard.CONFIG['branch']}" in calls[-1]
