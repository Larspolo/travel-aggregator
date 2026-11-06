"""A "Start after:" line that does not parse holds only its own ticket (#3055): a bad date or a #M that is no PR
(GitHub answers 404) must not stop the pick order of all tickets. One warning on stderr names the ticket and the line."""
import datetime
import subprocess

import dashboard
import pytest

NOW = datetime.datetime(2026, 10, 28, tzinfo=datetime.timezone.utc)


def issue(n, body=""):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": "P2"}], body=body)


def not_found(number):
    raise subprocess.CalledProcessError(1, ["gh", "api", f"pulls/{number}"], stderr="Not Found (HTTP 404)")


@pytest.mark.parametrize("line", ["Start after: 2026-10-28 24:00 UTC", "Start after: 2026-02-30 10:00 UTC",
                                  "Start after: 50 PRs after #2844"])
def test_a_bad_line_holds_only_its_ticket(line, capsys):
    issues = [issue(1), issue(2, f"## Goal\n{line}\n"), issue(3, "Start after: 2026-10-27 05:15 UTC")]
    assert [i["number"] for i in dashboard.candidates(issues, now=NOW, after=not_found)] == [1, 3]
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and "#2" in err[0] and line in err[0]


def test_good_lines_give_no_warning(capsys):
    issues = [issue(1), issue(2, "Start after: 1 PR after #7"), issue(3, "Start after: 2026-10-29 10:00 UTC")]
    assert [i["number"] for i in dashboard.candidates(issues, now=NOW, after={7: 1}.get)] == [1, 2]
    assert capsys.readouterr().err == ""
