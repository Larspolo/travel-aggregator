"""framework/tools/report.py writes the run report of autopilot step 8 in the format that framework/tools/health.py parses (#1701)."""
import health
import pytest
import report

USAGE = "Usage: 2026-10-27T15:58:13Z · usage 0.0% · resets 2026-10-27T20:50:00Z · runs 1 · week 0.0% · release 84.1%"
TOKENS = "Tokens: 0.55M eq · calls 34 · write 0.08M · read 3.10M · out 0.02M · peak 110k · base 66k (repo 9k) · sinks base 54%"


def test_the_report_parses_into_the_same_numbers(monkeypatch, capsys):
    monkeypatch.setattr(report, "tool", lambda *a: {"release.py": "Release bar", "tokens.py": "x\n" + TOKENS}[a[0]])
    monkeypatch.setattr(report, "git_lane", lambda: None)  # the run can set `git config travel-aggregator.lane` (#2093)
    report.main(["--text", "Did #1.", "--usage", USAGE, "--ticket", "1", "--size", "S", "--result", "pr #2",
                 "--setup", "2", "--checks", "1", "--checks-min", "4",
                 "--phases", "read=1,claim=1,code=1,verify=1,ci=0,conflict=0,report=1"])
    body = capsys.readouterr().out
    comments = [{"body": body}]
    assert body.startswith("Did #1.\n\nRelease bar\n\n" + USAGE + "\nMetrics: ticket #1 · size:S · pr #2 · 5 min ·")
    assert health.phase_minutes(comments) == {"read": 1, "claim": 1, "code": 1, "verify": 1, "ci": 0, "conflict": 0,
                                              "report": 1}
    assert health.setup_minutes(comments) == [2.0]
    assert health.lanes(comments) == {"opus": (1, 1, [5.0], [0.55])}
    assert health.pr_results(comments, [{"number": 2, "merged_at": "2026-10-27T16:00:00Z"}]) == ([2], [])
    assert health.SAMPLE.search(body) and health.TOKENS.search(body)
    assert body.endswith(report.FOOTER + "\n")


def test_two_tickets_and_a_lane():
    a = report.metrics(5, "size:M", "merged", 40, sinks="mc tests 8 min", phase="code=10,verify=18")
    b = report.metrics(6, "S", "none", phase="read=3", lane="haiku")
    assert a == ("Metrics: ticket #5 · size:M · merged · 40 min · setup 0 min · checks 0 · checks 0 min · time sinks: "
                 "mc tests 8 min · phases read 0 · claim 0 · code 10 · verify 18 · ci 0 · conflict 0 · report 0")
    assert b.startswith("Metrics: ticket #6 · size:S · none · 3 min ·") and b.endswith("· lane haiku")
    assert health.lanes([{"body": a + "\n" + b}]) == {"opus": (1, 1, [40.0], []), "haiku": (1, 0, [3.0], [])}


def test_an_unknown_phase_stops():
    with pytest.raises(ValueError, match="tests"):
        report.phases("read=1,tests=2")
