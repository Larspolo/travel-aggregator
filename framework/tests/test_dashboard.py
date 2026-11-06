"""The dashboard of the status issue: pick order and sections, with fixture data (no network)."""
import datetime

import dashboard


def issue(n, *names, body="", title=None, **kw):
    return dict(number=n, title=title or f"Ticket {n}", labels=[{"name": x} for x in names], body=body, **kw)


def test_pick_order():
    issues = [issue(9, "P2", "size:S"), issue(3, "P2"), issue(7, "P1"), issue(2, "P0", "needs-human"),
              issue(4, "P1", "in-progress"), issue(5, "P0", body="Depends on: #3"), issue(6, "P3", "epic"),
              issue(8, "P0", body="Depends on: #1, #99"), issue(10, "P1", "blocked"), issue(11),
              issue(12, "P0", pull_request={})]
    # #8 depends on closed issues only; #5 waits for the open #3; issues without a priority come last
    assert [i["number"] for i in dashboard.candidates(issues)] == [8, 7, 3, 9, 11]


def test_depends_on_open_pr():
    # #21 waits for the open PR #12 (#243); a "Depends on:" in the middle of a sentence is no dependency
    issues = [issue(12, "P0", pull_request={}), issue(21, "P1", body="Depends on: #12"),
              issue(22, "P1", body='Text: "Depends on: #12" names a PR.'), issue(23, "P2", "in-progress")]
    assert [i["number"] for i in dashboard.candidates(issues)] == [22]


def test_render_sections():
    old = ('<!-- agent-state: {"last_run": "2026-10-25T19:00:00Z", "runs": 15} -->\n## Agent status\n'
           "**Last run:** old text\n\n### Next up\n1. #4 stale\n\n### Process changes\n- 2026-10-25: a change\n"
           "\n_Updated 2026-10-25 18:00 UTC by the dashboard workflow._\n\n---\n_footer_")
    issues = [issue(1, "agent-status", body=old, title="Agent status"), issue(4, "P1", "in-progress"),
              issue(5, "needs-human", "P2"), issue(6, "P1", "size:M")]
    comments = {
        4: [{"body": "Started by `claude/a`."}, {"body": "Started by `claude/b`."},
            {"body": "Released: claimed twice by `claude/b`."}],
        5: [{"body": "Done.\n\nQuestion: is the castle too high?\n\n---\n_Generated_"}, {"body": "Started by `x`."}],
    }
    open_prs = [{"number": 20, "title": "T", "body": "Closes #4", "head": {"ref": "claude/a"}}]
    closed = [issue(3, title="Old", state_reason="completed", closed_at="2026-10-25T10:00:00Z"),
              issue(2, title="Dropped", state_reason="not_planned", closed_at="2026-10-25T11:00:00Z")]
    closed_prs = [{"number": 19, "title": "T", "body": "Closes #3", "merged_at": "2026-10-25T10:00:00Z"}]
    now = datetime.datetime(2026, 10, 25, 19, 30)
    body = dashboard.render(old, issues, comments, open_prs, closed, closed_prs, now)
    assert body.startswith('<!-- agent-state: {"last_run": "2026-10-25T19:00:00Z", "runs": 15} -->')
    assert "- #5 Ticket 5 – Question: is the castle too high?" in body
    assert "- #4 Ticket 4 – `claude/a`, PR #20" in body                    # claude/b released the ticket
    assert "1. #6 Ticket 6 (P1, size:M)" in body and "stale" not in body and "old text" not in body
    assert "- #3 Old – PR #19 (2026-10-25)" in body and "Dropped" not in body
    assert body.count("- 2026-10-25: a change") == 1 and body.count("_Updated ") == 1
    assert "_Updated 2026-10-25 19:30 UTC" in body
    # a second run keeps the same process section
    again = dashboard.render(body, issues, comments, open_prs, closed, closed_prs, now)
    assert again == body


def test_started_by():
    c = [{"body": f} for f in ("Started by `a`.", "Released: depends on #4, which is still open.",
                               "Started by `b`.", "Started by `c`.", "Released: claimed twice by `c`.")]
    assert dashboard.started_by(c) == "b"
    assert dashboard.started_by(c + [{"body": "Taken over by `d`: stalled."}]) == "d"
    assert dashboard.started_by([]) is None


def test_api_sends_json_with_token(monkeypatch):
    """With GITHUB_TOKEN, a body goes as JSON: without the header GitHub answers 415 (#345)."""
    import io
    sent = []
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(dashboard.urllib.request, "urlopen", lambda req: sent.append(req) or io.BytesIO(b"{}"))
    dashboard.api("issues/1", "PATCH", {"body": "b"})
    assert sent[0].get_header("Content-type") == "application/json"
