"""framework/tools/feedback.py lists an owner comment that no run handled, also after a stop of the runs of more than 6 hours
(#3060): the window starts 6 hours before the earlier of now and `last_run` of the status issue, at most 23 hours."""
import datetime

import feedback

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.timezone.utc)


def iso(hours):
    return f"{NOW - datetime.timedelta(hours=hours):%Y-%m-%dT%H:%M:%SZ}"


def comment(cid, hours):
    return {"id": cid, "body": "Do this", "user": {"login": feedback.OWNER}, "created_at": iso(hours),
            "performed_via_github_app": None, "issue_url": "https://api.github.com/repos/o/r/issues/5"}


def fake(monkeypatch, last_run, comments):
    """A fake GitHub: the status issue with `last_run`, the comments (oldest first) in pages of 100, no lock ref."""
    seen = []

    def api(path):
        if path == f"issues/{feedback.CONFIG['status']['issue']}":
            return {"body": f'<!-- agent-state: {{"last_run": "{last_run}", "runs": 3}} -->\n## Status'}
        return []

    def pages(path, limit=10):
        seen.append(path)
        since = path.split("since=")[1]
        found = [c for c in comments if c["created_at"] >= since] if path.startswith("issues/") else []
        return found[:limit * 100]

    monkeypatch.setattr(feedback, "api", api)
    monkeypatch.setattr(feedback, "pages", pages)
    return seen


def test_a_comment_after_a_stop_of_9_hours_is_listed(monkeypatch):
    fake(monkeypatch, iso(9), [comment(1, 8)])
    assert [c["id"] for c in feedback.fetch(now=NOW)] == [1]


def test_a_recent_last_run_keeps_the_window_of_6_hours(monkeypatch):
    seen = fake(monkeypatch, iso(5 / 60), [comment(1, 6.2), comment(2, 6)])
    assert [c["id"] for c in feedback.fetch(now=NOW)] == [2]
    assert seen[0] == f"issues/comments?since={iso(6 + 5 / 60)}"     # 6 hours before last_run


def test_the_window_is_at_most_23_hours(monkeypatch):
    seen = fake(monkeypatch, iso(48), [comment(1, 23.5), comment(2, 22)])
    assert [c["id"] for c in feedback.fetch(now=NOW)] == [2]
    assert seen[0] == f"issues/comments?since={iso(23)}"


def test_no_status_issue_keeps_the_window_of_6_hours(monkeypatch):
    fake(monkeypatch, iso(9), [comment(1, 8), comment(2, 1)])
    monkeypatch.setattr(feedback, "api", lambda path: (_ for _ in ()).throw(OSError("no access")))
    assert [c["id"] for c in feedback.fetch(now=NOW)] == [2]


def test_the_page_limit_covers_the_window(monkeypatch):
    comments = [dict(comment(i, 20 - i / 60), body=f"c{i}") for i in range(1200)]     # 1200 comments in 20 hours
    fake(monkeypatch, iso(20), comments)
    assert feedback.fetch(now=NOW)[-1]["id"] == 1199
