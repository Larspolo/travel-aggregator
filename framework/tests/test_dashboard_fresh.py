"""framework/tools/dashboard.py reads the status issue again after all other reads (#3002): a state comment or a process-change
line that a run writes while the dashboard reads GitHub stays in the PATCH body."""
import sys
import types

import dashboard
import feedback

OLD = ('<!-- agent-state: {"last_run": "2026-10-28T08:35:33Z", "runs": 721, "review_prs": 50} -->\n## Agent status\n\n'
       "### Process changes\n- 2026-10-27: an old change (PR #10)\n")
NEW = ('<!-- agent-state: {"last_run": "2026-10-28T08:37:08Z", "runs": 722, "review_prs": 100} -->\n## Agent status\n\n'
       "### Process changes\n- 2026-10-28: a new change (PR #11)\n- 2026-10-27: an old change (PR #10)\n")


def test_a_write_during_the_reads_stays(monkeypatch):
    status = dict(number=1, title="Agent status", labels=[{"name": dashboard.STATUS}], body=OLD)
    work = dict(number=5, title="A ticket", labels=[{"name": "in-progress"}, {"name": "P2"}], body="")
    patches = []

    def pages(path, limit=10):
        if path == "issues/5/comments":                         # a run reports while the dashboard reads
            status["body"] = NEW
        return {"issues?state=open": [dict(status, body=OLD), work]}.get(path, [])

    def api(path, method="GET", data=None):
        if method == "PATCH":
            patches.append((path, data["body"]))
        return dict(status) if path == "issues/1" else []
    monkeypatch.setattr(dashboard, "pages", pages)
    monkeypatch.setattr(dashboard, "api", api)
    monkeypatch.setattr(feedback, "fetch", lambda: [])
    monkeypatch.setitem(sys.modules, "dashboard_data", types.SimpleNamespace(accounts=lambda: []))  # a project tool (#4239)
    assert dashboard.main([]) == 0
    (path, body), = patches
    assert path == "issues/1"
    assert '"runs": 722' in body and '"review_prs": 100' in body and "a new change (PR #11)" in body
    assert "an old change (PR #10)" in body


def test_no_patch_when_the_fresh_body_is_the_same(monkeypatch):
    status = dict(number=1, title="Agent status", labels=[{"name": dashboard.STATUS}], body=OLD)
    patches = []

    def api(path, method="GET", data=None):
        if method == "PATCH":
            patches.append(data["body"])
            status["body"] = data["body"]
        return dict(status) if path == "issues/1" else []
    monkeypatch.setattr(dashboard, "pages", lambda path, limit=10: [dict(status)] if path == "issues?state=open" else [])
    monkeypatch.setattr(dashboard, "api", api)
    monkeypatch.setattr(feedback, "fetch", lambda: [])
    monkeypatch.setitem(sys.modules, "dashboard_data", types.SimpleNamespace(accounts=lambda: []))  # a project tool (#4239)
    assert dashboard.main([]) == 0 and len(patches) == 1
    assert dashboard.main([]) == 0 and len(patches) == 1            # the same body: "no change"
