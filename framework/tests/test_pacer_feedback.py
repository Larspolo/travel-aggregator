"""#294: owner comments wait while each pacer run gets a brief, because a brief skips step 3.
One main run per cycle gets no brief then, and does the feedback step itself."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import pacer  # noqa: E402


def briefs(monkeypatch, waiting):
    monkeypatch.setattr(pacer, "red_main", lambda: False)
    monkeypatch.setattr(pacer, "unanswered", lambda: waiting)
    monkeypatch.setattr(pacer, "queues", lambda *a: {"main": [{"number": 7}, {"number": 8}], "haiku": [{"number": 9}]})
    monkeypatch.setattr(pacer, "stuck", lambda *a: [])
    monkeypatch.setattr(pacer.usage, "sample_line", lambda *a, **k: "Usage: x")
    return pacer.Briefs([("main",), ("haiku",)], {"open": [], "refs": []}, None, {}, dry=True)


def test_one_main_run_gets_no_brief_while_owner_comments_wait(monkeypatch):
    b = briefs(monkeypatch, True)
    assert b.take("haiku")[0] == 9
    assert b.take("main") is None
    assert b.take("main")[0] == 7


def test_all_runs_get_a_brief_when_no_comment_waits(monkeypatch):
    b = briefs(monkeypatch, False)
    assert b.take("main")[0] == 7


def test_a_failed_feedback_read_keeps_the_briefs(monkeypatch):
    import feedback
    monkeypatch.setattr(feedback, "fetch", lambda: (_ for _ in ()).throw(RuntimeError("no access")))
    assert pacer.unanswered() is False
