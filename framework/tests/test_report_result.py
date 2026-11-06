"""report.py writes the result of a `Metrics:` line only in a form that health.py counts (2026-10-31: "PR #N", "pr"
and "merged-pending" of the main lane counted as no PR)."""
import health
import pytest
import report

USAGE = "Usage: 2026-10-27T15:58:13Z · usage 0.0% · resets 2026-10-27T20:50:00Z · runs 1 · week 0.0% · release 84.1%"


def run(monkeypatch, capsys, *results):
    monkeypatch.setattr(report, "tool", lambda *a: {"release.py": "", "tokens.py": ""}[a[0]])
    monkeypatch.setattr(report, "git_lane", lambda: "main")
    argv = ["--text", "Did it.", "--usage", USAGE]
    for i, r in enumerate(results):
        argv += ["--ticket", str(i + 1), "--size", "S", "--result", r, "--phases", "read=1"]
    report.main(argv)
    return [{"body": capsys.readouterr().out}]


def test_each_written_result_counts_in_health(monkeypatch, capsys):
    comments = run(monkeypatch, capsys, "PR #12", "pr#13", "merged", "Closed", "none")
    assert "· pr #12 ·" in comments[0]["body"] and "· closed ·" in comments[0]["body"]
    assert health.lanes(comments)["main"][:2] == (5, 3)


@pytest.mark.parametrize("bad", ["pr", "merged-pending", "check-bug", "PR"])
def test_a_result_of_another_form_stops_the_report(monkeypatch, capsys, bad):
    with pytest.raises(SystemExit):
        run(monkeypatch, capsys, bad)
    assert "pr #N" in capsys.readouterr().err
