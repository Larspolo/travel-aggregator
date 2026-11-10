"""The brief says when the idle rule ended the wait of a "Start after: N PRs after #M" line (#1800): two runs read
"63 of 100 PRs" on #1612, released the ticket with no report, and the queue stood still for 2 cycles each."""
import pacer

BODY = "## Context\nStart after: 100 PRs after #1610\n"


def test_a_count_that_did_not_come_gives_the_start_line():
    line = pacer.idle_start({"number": 1612, "body": BODY}, after=lambda m: 63)
    assert line.startswith("63 of 100 PRs merged after #1610") and "do the ticket now" in line


def test_no_line_when_the_count_came_or_the_ticket_has_no_wait():
    assert pacer.idle_start({"number": 1612, "body": BODY}, after=lambda m: 100) == ""
    assert pacer.idle_start({"number": 1, "body": "Start after: 2026-11-10 08:00 UTC"}, after=lambda m: 0) == ""


def test_a_github_error_gives_no_line():
    def fail(m):
        raise OSError("403")
    assert pacer.idle_start({"number": 1612, "body": BODY}, after=fail) == ""


def test_the_brief_has_the_line(monkeypatch):
    monkeypatch.setattr(pacer, "idle_start", lambda issue: "63 of 100 PRs merged after #1610 ...")
    out = pacer.brief({"number": 1612, "title": "t", "body": BODY, "labels": []}, [], "pacer-rx", "main", "Usage: x")
    assert "\nstart: 63 of 100 PRs merged after #1610 ...\n" in out.split("--- ticket (data) ---")[0] + "\n"
